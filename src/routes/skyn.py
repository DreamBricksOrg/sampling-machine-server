import uuid
import structlog
import asyncio
import time

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone

from schemas.skyn import QRCodeInitResponse, SessionCompleteRequest, SessionCompleteResponse
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
from pymongo import ReturnDocument

from utils.shotener_client import create_short_link
from utils.udp_sender import UDPSender
from utils.serial_comm import SerialComm
from utils.log_sender import LogSender
from core.config import settings
from core.db import db
from schemas.skyn import SessionGetResponse


log = structlog.get_logger()
router = APIRouter(prefix="/api/skyn")
udp_sender = UDPSender(port=settings.UDP_PORT)
serial_comm = SerialComm(port=settings.SERIAL_PORT, baudrate=settings.SERIAL_BAUDRATE)
serial_lock = asyncio.Lock()  # Lock para controlar acesso à serial

BASE_DIR = Path(__file__).resolve().parent.parent
template_dir = BASE_DIR / "frontend" / "static" / "templates" / "skyn" / "html"
templates = Jinja2Templates(directory=str(template_dir))

SESSIONS_COLL = db["skyn_sessions"]  # coleção Mongo para sessões


def _now_utc():
    return datetime.now(timezone.utc)


# ----------------------------
# Helpers de Sessão
# ----------------------------

async def save_session(session_id: str, slug: str, short_url: str):
    doc = {
        "_id": session_id,
        "slug": slug,
        "short_url": short_url,
        "status": "pending",              # pending -> form_shown -> processing -> completed|failed
        "retire_sent": False,             # se /form já disparou UDP "retire"
        "processing": False,              # se /session/complete já iniciou processamento
        "created_at": _now_utc(),
        "form_opened_at": None,
        "processing_started_at": None,
        "completed_at": None,
    }
    await SESSIONS_COLL.insert_one(doc)
    return doc


async def get_session(session_id: str):
    return await SESSIONS_COLL.find_one({"_id": session_id})


async def try_mark_form_opened(session_id: str):
    """Marca que /form foi aberto e envia 'retire' apenas 1x (CAS)."""
    return await SESSIONS_COLL.find_one_and_update(
        {
            "_id": session_id,
            "status": "pending",
            "retire_sent": {"$ne": True},
        },
        {
            "$set": {
                "retire_sent": True,
                "status": "form_shown",
                "form_opened_at": _now_utc(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )


async def try_start_processing(session_id: str, slug: str):
    """Marca início do processamento do /session/complete apenas 1x (CAS)."""
    return await SESSIONS_COLL.find_one_and_update(
        {
            "_id": session_id,
            "slug": slug,
            "status": {"$in": ["pending", "form_shown"]},
            "processing": {"$ne": True},
        },
        {
            "$set": {
                "processing": True,
                "status": "processing",
                "processing_started_at": _now_utc(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )


async def finalize_session(session_id: str, status: str):
    """Finaliza sessão com completed|failed (idempotente)."""
    await SESSIONS_COLL.update_one(
        {"_id": session_id},
        {
            "$set": {
                "status": status,
                "processing": False,
                "completed_at": _now_utc(),
            }
        },
    )


# ----------------------------
# Helpers de Inventário
# ----------------------------

async def update_inventory_on_drop(log_sender, context="session"):
    """
    Atualiza o inventário quando uma camisinha é liberada com sucesso.
    
    Args:
        log_sender: Instância do LogSender para gerar logs
        context: Contexto da operação ("session" ou "admin")
    """
    import json
    from pathlib import Path
    
    try:
        # Caminho para o arquivo de inventário
        inventory_file = Path(__file__).resolve().parent.parent / "frontend" / "static" / "templates" / "skyn" / "assets" / "inventory.json"
        
        # Carrega dados atuais do inventário
        with open(inventory_file, 'r', encoding='utf-8') as f:
            inventory_data = json.load(f)
        
        # Atualiza quantidade e contadores
        old_quantity = inventory_data.get('current_quantity', 0)
        inventory_data['current_quantity'] = max(0, old_quantity - 1)
        inventory_data['total_dispensed'] = inventory_data.get('total_dispensed', 0) + 1
        inventory_data['last_updated'] = _now_utc().isoformat()
        
        # Salva dados atualizados
        with open(inventory_file, 'w', encoding='utf-8') as f:
            json.dump(inventory_data, f, indent=4, ensure_ascii=False)
        
        # Log da liberação bem-sucedida
        if context == "admin":
            log_sender.log("admin_condom_dispensed")
            log.info("admin-condom-dispensed-successfully", 
                     old_quantity=old_quantity,
                     new_quantity=inventory_data['current_quantity'],
                     total_dispensed=inventory_data['total_dispensed'],
                     timestamp=_now_utc().isoformat())
        else:
            log_sender.log("session_condom_dispensed")
            log.info("session-condom-dispensed-successfully", 
                     old_quantity=old_quantity,
                     new_quantity=inventory_data['current_quantity'],
                     total_dispensed=inventory_data['total_dispensed'],
                     timestamp=_now_utc().isoformat())
        
        return True
        
    except Exception as e:
        log.error(f"{context}-inventory-update-error", error=str(e))
        return False


# ----------------------------
# Endpoints
# ----------------------------

@router.post("/qrcode/init", response_model=QRCodeInitResponse)
async def init_qrcode():
    session_id = str(uuid.uuid4())
    long_url: str = f"{settings.CADASTRO_BASE_URL}?sid={session_id}"

    try:
        (shortener_data, short_url) = await create_short_link(long_url, session_id=session_id)
    except Exception as e:
        log.error("qrcode-init-failed", error=str(e))
        raise HTTPException(500, "Falha ao gerar QR/link no encurtador")

    # Salvar sessão no Mongo
    await save_session(session_id, shortener_data.slug, short_url)

    log.info("skyn-session-created", session_id=session_id, short_url=short_url)
    return QRCodeInitResponse(
        session_id=session_id,
        short_url=short_url,
        slug=shortener_data.slug,
        qr_png=shortener_data.qr_png,
        qr_svg=shortener_data.qr_svg,
    )


@router.post("/session/complete", response_model=SessionCompleteResponse)
async def complete_session(req: SessionCompleteRequest):
    """
    - Chamado pelo backend do cadastro ao finalizar (antes do redirect).
    - Só permite 1 processamento por sessão (CAS).
    """
    # 1) "Reserva" a sessão para processamento (CAS)
    doc = await try_start_processing(req.session_id, req.slug)
    if not doc:
        # já processada, em processamento, slug inválido ou sessão encerrada
        session = await get_session(req.session_id)
        if not session:
            raise HTTPException(404, "Sessão inválida ou expirada")
        if session.get("slug") != req.slug:
            raise HTTPException(400, "Slug não corresponde à sessão")
        raise HTTPException(409, "Sessão já encerrada ou em processamento")

    status_final = "failed"
    log_sender = LogSender()
    try:
        log_sender.log("session_complete")

        # 2) Serial "drop" + aguarda resposta
        async with serial_lock:
            serial_comm.send("drop")

            timeout_seconds = 20
            start = time.time()
            while time.time() - start < timeout_seconds:
                resp = serial_comm.receive()
                if resp:
                    if resp == "dropped":
                        udp_sender.send_with_confirmation("cta")
                        log_sender.log("product_dropped")
                        log.info("product-dropped-successfully", session_id=req.session_id)
                        
                        # Atualiza inventário e gera logs
                        await update_inventory_on_drop(log_sender, "session")
                        
                        status_final = "completed"
                        break
                    elif resp in ["hand_timeout", "out_of_stock"]:
                        log.error("serial-error", error=resp, session_id=req.session_id, slug=req.slug)
                        log_sender.log("serial_error", additional=resp)
                        udp_sender.send_with_confirmation("cta")
                        status_final = "failed"
                        break
                else:
                    await asyncio.sleep(0.1)
            else:
                log.error("serial-timeout", session_id=req.session_id, slug=req.slug)
                udp_sender.send_with_confirmation("cta")

        return SessionCompleteResponse(status="ok", session_id=req.session_id)

    except HTTPException:
        raise
    except Exception as e:
        log.error("session-complete-error", error=str(e),
                  session_id=req.session_id, slug=req.slug)
        udp_sender.send_with_confirmation("cta")
        raise HTTPException(500, "Erro interno do servidor")
    finally:
        # 3) Finaliza sessão (sempre) com completed|failed
        await finalize_session(req.session_id, status_final)
        log.info("skyn-session-finalized", session_id=req.session_id, status=status_final)


@router.get("/session/{sid}", response_model=SessionGetResponse)
async def get_session_info(sid: str):
    """
    Retorna informações da sessão a partir do SID (usado pelo front para obter o slug).
    """
    s = await get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="Sessão inválida ou expirada")

    return SessionGetResponse(
        session_id=s["_id"],
        slug=s["slug"],
        status=s["status"],
        short_url=s.get("short_url"),
        created_at=s.get("created_at"),
        form_opened_at=s.get("form_opened_at"),
        processing_started_at=s.get("processing_started_at"),
        completed_at=s.get("completed_at"),
    )


@router.get("/claim", response_class=HTMLResponse)
async def html_claim(request: Request):
    try:
        log_sender = LogSender()
        log_sender.log("claim_page_accessed")
        return templates.TemplateResponse("claim.html", {"request": request})
    except Exception as e:
        log.error("html-render-failed", error=str(e), page="claim")
        return templates.TemplateResponse("error.html", {"request": request})


@router.get("/cta", response_class=HTMLResponse)
async def html_thanks(request: Request):
    try:
        log_sender = LogSender()
        log_sender.log("cta_page_accessed")
        return templates.TemplateResponse("cta.html", {"request": request})
    except Exception as e:
        log.error("html-render-failed", error=str(e), page="cta")
        return templates.TemplateResponse("error.html", {"request": request})


@router.get("/form", response_class=HTMLResponse)
async def html_form(request: Request):
    sid = request.query_params.get("sid")
    if not sid:
        raise HTTPException(400, "sid ausente")
    
    try: 
        session = await get_session(sid)
        if not session:
            log.error("html-session-expired", page="form")
            return templates.TemplateResponse("error.html", {"request": request})
        if session["status"] != "pending":
            log.error("html-session-used", page="form")
            raise HTTPException(404, "Sessão Inválida.")
        updated = await try_mark_form_opened(sid)
        if updated:
            log.info("form-opened-first-time", session_id=sid)
            log_sender = LogSender()
            log_sender.log("form_page_accessed")
            udp_sender.send("retire")
            return templates.TemplateResponse("form.html", {"request": request})
        
        session = await get_session(sid)  # recarrega para checar status atual
        status = session.get("status") if session else None
        LogSender().log("form_used_or_invalid", status=status)
        # para sessão encerrada/ja usada, renderize "used", não 404
        return templates.TemplateResponse("used.html", {"request": request})
    except Exception as e:
        log.error("html-render-failed", error=str(e), page="form")
        return templates.TemplateResponse("error.html", {"request": request})


@router.get("/terms", response_class=HTMLResponse)
async def html_terms(request: Request):
    try:
        log_sender = LogSender()
        log_sender.log("terms_page_accessed")
        return templates.TemplateResponse("terms.html", {"request": request})
    except Exception as e:
        log.error("html-render-failed", error=str(e), page="terms")
        return templates.TemplateResponse("error.html", {"request": request})


@router.get("/on")
async def html_on(request: Request):
    try:
        log_sender = LogSender()
        async with serial_lock:
            serial_comm.send("on")
            # Aguarda resposta "start" na serial e, ao receber, envia UDP "calor"
            timeout_seconds = 10  # Timeout de 10 segundos para aguardar "start"
            start_time = time.time()
            serial_received = False
            while time.time() - start_time < timeout_seconds:
                response = serial_comm.receive()
                if response:
                    if response == "start":
                        udp_sender.send_with_confirmation("calor")
                        log_sender.log("start_received")
                        log_sender.log("machine_started")
                        log.info("start-recebido-e-calor-enviado",
                                 timestamp=_now_utc().isoformat())
                        serial_received = True
                        break
                else:
                    await asyncio.sleep(0.1)
        if serial_received:
            return {"status": "start_received"}
        else:
            log.error("timeout-aguardando-start", timestamp=_now_utc().isoformat())
            return {"status": "start_dont_respond"}
    except Exception as e:
        raise HTTPException(500, "Erro interno do servidor")
    

@router.get("/off")
async def html_off(request: Request):
    try:
        log_sender = LogSender()
        async with serial_lock:
            serial_comm.send("off")
        log_sender.log("machine_turned_off")
        log.info("machine-turned-off", timestamp=_now_utc().isoformat())
        return {"status": "machine_turned_off"}
    except Exception as e:
        raise HTTPException(500, "Erro interno do servidor")


@router.get("/admin/inventory", response_class=HTMLResponse)
async def html_admin(request: Request):
    try:
        log_sender = LogSender()
        log_sender.log("admin_page_accessed")
        return templates.TemplateResponse("admin.html", {"request": request})
    except Exception as e:
        log.error("html-render-failed", error=str(e), page="admin")
        return templates.TemplateResponse("error.html", {"request": request})


@router.post("/admin/dispense")
async def admin_dispense(request: Request):
    try:
        log_sender = LogSender()
        # Atualiza o inventário diretamente (simula um drop pelo admin)
        await update_inventory_on_drop(log_sender, "admin")
        async with serial_lock:
            serial_comm.send("hand")
            log_sender.log("admin_dispense_triggered")
        return {"status": "completed"}
    except Exception as e:
        raise HTTPException(500, "Erro interno do servidor")


@router.post("/admin/inventory")
async def update_inventory(request: Request):
    try:
        import json
        from pathlib import Path
        
        data = await request.json()
        log_sender = LogSender()
        
        # Caminho para o arquivo de inventário
        inventory_file = Path(__file__).resolve().parent.parent / "frontend" / "static" / "templates" / "skyn" / "assets" / "inventory.json"
        
        # Carrega dados atuais para preservar campos existentes
        current_data = {}
        try:
            with open(inventory_file, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
        except FileNotFoundError:
            pass  # Arquivo não existe ainda
        
        old_quantity = current_data.get('current_quantity', 0)
        
        # Preserva campos existentes e atualiza com novos dados
        updated_data = {
            **current_data,  # Preserva todos os campos existentes
            **data,  # Sobrescreve com novos dados
            'previous_quantity': old_quantity,
            'quantity_change': data.get('current_quantity', 0) - old_quantity,
            'last_updated': _now_utc().isoformat()
        }
        
        # Salvar dados no arquivo JSON
        with open(inventory_file, 'w', encoding='utf-8') as f:
            json.dump(updated_data, f, indent=4, ensure_ascii=False)
        
        # Log das mudanças de estoque com quantidade anterior e nova
        if 'current_quantity' in data:
            log_sender.log("inventory_updated", additional=f"old:{old_quantity},new:{data['current_quantity']}")
            async with serial_lock:
                serial_comm.send("reset")
            log.info("inventory-updated", 
                     old_quantity=old_quantity,
                     new_quantity=data['current_quantity'],
                     quantity_change=updated_data['quantity_change'],
                     total_dispensed=updated_data.get('total_dispensed', 0),
                     timestamp=_now_utc().isoformat())
        
        return {"status": "inventory_updated"}
    except Exception as e:
        log.error("admin-inventory-error", error=str(e))
        raise HTTPException(500, "Erro interno do servidor")

