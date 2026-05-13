import structlog
from fastapi import APIRouter, HTTPException, Query, Request

from infrastructure.config import settings
from integrations.logcenter.log_sender import LogSender
from .schemas import DropRequest
from .services import InventoryService, MachineService

log = structlog.get_logger()
router = APIRouter(prefix="/api/docile")


def _verify_drop_code(drop_code: str) -> None:
    if drop_code != settings.DROP_CODE:
        raise HTTPException(403, "Drop code inválido")


@router.post("/drop")
async def drop(payload: DropRequest):
    _verify_drop_code(payload.drop_code)
    try:
        await MachineService().drop()
        return {"status": "drop_sent"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Erro interno do servidor")


@router.post("/drop/wait")
async def drop_waiting_callback(payload: DropRequest, slug: str = Query("")):
    _verify_drop_code(payload.drop_code)
    try:
        status = await MachineService().drop_waiting_callback(slug=slug)
        return {"status": status}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Erro interno do servidor")


@router.get("/on")
async def machine_on():
    try:
        return await MachineService().turn_on()
    except Exception:
        raise HTTPException(500, "Erro interno do servidor")


@router.get("/off")
async def machine_off():
    try:
        return await MachineService().turn_off()
    except Exception:
        raise HTTPException(500, "Erro interno do servidor")


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
