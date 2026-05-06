from dns.rdtypes.IN import NSAP_PTR
import os
import structlog
from pathlib import Path
import sys
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sentry_sdk import init as sentry_init
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

from core.db import init_db
from core.exceptions import AppError
from core.config import settings

import logging
import structlog
from logcenter_sdk.config import LogCenterConfig
from logcenter_sdk.sender import LogCenterSender
from logcenter_sdk.middleware import LogCenterAuditMiddleware

from routes.api import router as api_router
from routes.registrations import router as reg_router
from routes.auth import router as auth_router
from routes.admin import router as admin_router
from routes.machine import router as machine_router

from middlewares.replay_guard import ReplayGuardMiddleware


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = os.path.join(BASE_DIR, "static")

logging.basicConfig(level=logging.INFO, format="%(message)s")

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

log = structlog.get_logger(__name__)

cfg = LogCenterConfig(
    base_url=(settings.LOG_API or "").rstrip("/"),
    project_id=settings.LOG_PROJECT_ID,
    api_key=settings.LOG_API_KEY,
    enabled=True,
)
sender = LogCenterSender(cfg)

try:
    import sentry_sdk
    from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
    SENTRY_AVAILABLE = True
except Exception:
    SENTRY_AVAILABLE = False



@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.log_sender = sender

    await init_db()

    async def _delayed_startup_log():
        await asyncio.sleep(0.3)
        await sender.send(
            level="INFO",
            message="Hershey's Capibarra startup",
            status="OK",
            tags=["startup"],
            data={"env": settings.ENV, "version": "0.1.0-dev"},
            spool_on_fail=False,
        )

    asyncio.create_task(_delayed_startup_log())

    yield

    # === SHUTDOWN ===
    try:
        await sender.send(
            level="INFO",
            message="Hershey's Capibarra shutdown",
            status="OK",
            tags=["shutdown"],
            data={"env": settings.ENV, "version": "0.1.0-dev"},
            spool_on_fail=False
        )
    finally:
        await sender.stop_background_flush()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, version="0.1.0-dev", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.SENTRY_DSN and SENTRY_AVAILABLE:
        sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.2)
        app.add_middleware(SentryAsgiMiddleware)

    app.add_middleware(ReplayGuardMiddleware, ttl_seconds=4)

    app.mount("/src/static", StaticFiles(directory="src/static"), name="src-static")
    app.mount("/static", StaticFiles(directory="src/static"), name="static")


    app.include_router(api_router)
    app.include_router(reg_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(machine_router)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    }
                },
            )


    return app
