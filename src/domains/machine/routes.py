import structlog
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from integrations.logcenter.log_sender import LogSender
from .repositories import BASE_DIR
from .schemas import QRCodeInitResponse, SessionCompleteRequest, SessionCompleteResponse, SessionGetResponse
from .services import InventoryService, MachineService

log = structlog.get_logger()
router = APIRouter(prefix="/api/docile")
templates = Jinja2Templates(directory=str(BASE_DIR / "static" / "docile" / "html"))


@router.post("/qrcode/init", response_model=QRCodeInitResponse)
async def init_qrcode():
    return await MachineService().init_qrcode()


@router.post("/session/complete", response_model=SessionCompleteResponse)
async def complete_session(req: SessionCompleteRequest):
    return await MachineService().complete_session(req)


@router.get("/session/{sid}", response_model=SessionGetResponse)
async def get_session_info(sid: str):
    return await MachineService().get_session_info(sid)


@router.get("/claim", response_class=HTMLResponse)
async def html_claim(request: Request):
    return render_logged_page(request, "claim.html", "claim_page_accessed", "claim")


@router.get("/cta", response_class=HTMLResponse)
async def html_thanks(request: Request):
    return render_logged_page(request, "cta.html", "cta_page_accessed", "cta")


@router.get("/form", response_class=HTMLResponse)
async def html_form(request: Request):
    sid = request.query_params.get("sid")
    if not sid:
        raise HTTPException(400, "sid ausente")
    try:
        template_name = await MachineService().open_form(sid)
        return templates.TemplateResponse(template_name, {"request": request})
    except HTTPException:
        raise
    except Exception as exc:
        log.error("html-render-failed", error=str(exc), page="form")
        return templates.TemplateResponse("error.html", {"request": request})


@router.get("/terms", response_class=HTMLResponse)
async def html_terms(request: Request):
    return render_logged_page(request, "terms.html", "terms_page_accessed", "terms")


@router.get("/on")
async def html_on():
    try:
        return await MachineService().turn_on()
    except Exception:
        raise HTTPException(500, "Erro interno do servidor")


@router.get("/off")
async def html_off():
    try:
        return await MachineService().turn_off()
    except Exception:
        raise HTTPException(500, "Erro interno do servidor")


@router.get("/admin/inventory", response_class=HTMLResponse)
async def html_admin(request: Request):
    return render_logged_page(request, "admin.html", "admin_page_accessed", "admin")


@router.post("/admin/dispense")
async def admin_dispense():
    try:
        return await MachineService().admin_dispense()
    except Exception:
        raise HTTPException(500, "Erro interno do servidor")


@router.post("/admin/inventory")
async def update_inventory(request: Request):
    try:
        return await InventoryService().update(await request.json(), LogSender())
    except Exception as exc:
        log.error("admin-inventory-error", error=str(exc))
        raise HTTPException(500, "Erro interno do servidor")


def render_logged_page(request: Request, template_name: str, event: str, page: str):
    try:
        LogSender().log(event)
        return templates.TemplateResponse(template_name, {"request": request})
    except Exception as exc:
        log.error("html-render-failed", error=str(exc), page=page)
        return templates.TemplateResponse("error.html", {"request": request})
