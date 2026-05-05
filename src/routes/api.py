import structlog
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


log = structlog.get_logger()
router = APIRouter(prefix="/api")

BASE_DIR = os.path.dirname(__file__) 
TEMPLATES_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend", "static", "templates"))
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def page_home(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})

@router.get("/user", include_in_schema=False)
async def page_user(request: Request):
    return templates.TemplateResponse("admin/user.html", {"request": request})

@router.get("/admin", include_in_schema=False)
async def page_admin(request: Request):
    return templates.TemplateResponse("admin/admin.html", {"request": request})