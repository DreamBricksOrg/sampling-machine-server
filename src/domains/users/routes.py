from pathlib import Path
from typing import List

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import EmailStr
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from infrastructure.config import settings
from integrations.logcenter.log_sender import LogSender
from .schemas import (
    QRCodeInitResponse,
    SessionCompleteRequest,
    SessionCompleteResponse,
    SessionGetResponse,
    UserGetResponse,
    UserInitRequest,
    UserInitResponse,
    UserPickupRequest,
    UserPickupResponse,
    UserUpdateRequest,
    SessionIsCompleteRequest,
    SessionIsCompleteResponse,
)
from .repositories import DEFAULT_COLLECTION
from .services import SessionService, UserService, CurrentSessionService

_BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(_BASE_DIR / "static" / "sample" / "html"))

router = APIRouter(prefix="/api/users")
session_router = APIRouter(prefix="/api/sample")


def service_for(collection: str) -> UserService:
    return UserService.for_collection(collection)


@router.post("/", response_model=UserInitResponse)
async def create_user(payload: UserInitRequest, request: Request, collection: str = Query(DEFAULT_COLLECTION)):
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip:
        ip = request.client.host
    payload.ip = ip
    return await service_for(collection).create_user(payload)


@router.get("/", response_model=List[UserGetResponse])
async def list_users(collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).list_users()


@router.get("/email/{email}", response_model=UserGetResponse)
async def get_user_by_email(email: EmailStr, collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).get_user_by_email(email)


@router.get("/{user_id}", response_model=UserGetResponse)
async def get_user(user_id: str, collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).get_user(user_id)


@router.put("/{user_id}", response_model=UserGetResponse)
async def update_user(user_id: str, update: UserUpdateRequest, collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).update_user(user_id, update)


@router.delete("/{user_id}")
async def delete_user(user_id: str, collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).delete_user(user_id)


@router.post("/pickup", response_model=UserPickupResponse)
async def register_pickup(payload: UserPickupRequest = Body(...), collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).register_pickup(payload)


@router.post("/eligibility/refresh")
async def refresh_eligibility(collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).refresh_eligibility()


@session_router.post("/session/complete", response_model=SessionCompleteResponse)
async def complete_session(payload: SessionCompleteRequest):
    return await SessionService().complete_session(payload)

@session_router.get("/session/complete/{sid}",response_model=SessionIsCompleteResponse)
async def is_session_complete(sid: str):
    session = await SessionService().get_session_info(sid)
    if session.status == "completed":
        return {"is_complete": True}
    else:
        return {"is_complete": False}


@session_router.post("/session/current/complete")
async def complete_current_session():
    return await SessionService().complete_current_session()

@session_router.post("/clear/current")
async def clear_current_session():
    await CurrentSessionService().clear_current_session()


@session_router.post("/qrcode/init", response_model=QRCodeInitResponse)
async def init_qrcode():
    return await SessionService().init_qrcode()

@session_router.get("/qrcode/static")
async def get_static_link():
    _id = await CurrentSessionService().get_current_id()
    if _id is None:
        qr_code_init_response = await SessionService().init_qrcode()
        long_url = f"{settings.CADASTRO_BASE_URL}?sid={qr_code_init_response.session_id}"
        _id = qr_code_init_response.session_id
        await CurrentSessionService().update_current(_id)
    else:
        long_url = f"{settings.CADASTRO_BASE_URL}?sid={_id}"
        
    return RedirectResponse(url=f"{long_url}", status_code=302)


@session_router.get("/session/{sid}", response_model=SessionGetResponse)
async def get_session_info(sid: str):
    return await SessionService().get_session_info(sid)


@session_router.get("/claim", response_class=HTMLResponse)
async def html_claim(request: Request):
    return _render_logged_page(request, "claim.html", "claim_page_accessed", "claim")


@session_router.get("/welcome", response_class=HTMLResponse)
async def html_welcome(request: Request):
    return _render_logged_page(request, "welcome.html", "welcome_page_accessed", "welcome")


@session_router.get("/form", response_class=HTMLResponse)
async def html_form(request: Request):
    import structlog
    log = structlog.get_logger()
    sid = request.query_params.get("sid")
    if not sid:
        raise HTTPException(400, "sid ausente")
    try:
        template_name = await SessionService().open_form(sid)
        return templates.TemplateResponse(request=request, name=template_name, context={},)
    except HTTPException:
        raise
    except Exception as exc:
        log.error("html-render-failed", error=str(exc), page="form")
        return templates.TemplateResponse("error.html", {"request": request})


@session_router.get("/terms", response_class=HTMLResponse)
async def html_terms(request: Request):
    return templates.TemplateResponse(request=request, name="terms.html", context={"use_form": settings.USE_FORM})

@session_router.get("/finish", response_class=HTMLResponse)
async def html_finish(request: Request):
    return _render_logged_page(request, "finish.html", "finish_page_accessed", "finish")

def _render_logged_page(
    request: Request,   
    template_name: str,
    event: str,
    page: str,
):
    import structlog
    log = structlog.get_logger()
    try:
        LogSender().log(event)

        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={},
        )

    except Exception:
        log.exception("html-render-failed", page=page)

        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={},
        )
