import asyncio
import time
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException

from infrastructure.config import settings
from integrations.logcenter.log_sender import LogSender
from integrations.shortener.client import create_short_link
from infrastructure.hardware.serial_comm import SerialComm
from infrastructure.hardware.udp_sender import UDPSender
from .repositories import InventoryRepository, SessionRepository
from .schemas import QRCodeInitResponse, SessionCompleteRequest, SessionCompleteResponse, SessionGetResponse

log = structlog.get_logger()
_udp_sender: UDPSender | None = None
_serial_comm: SerialComm | None = None
serial_lock = asyncio.Lock()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_udp_sender() -> UDPSender:
    global _udp_sender
    if _udp_sender is None:
        _udp_sender = UDPSender(port=settings.UDP_PORT)
    return _udp_sender


def get_serial_comm() -> SerialComm:
    global _serial_comm
    if _serial_comm is None:
        _serial_comm = SerialComm(port=settings.SERIAL_PORT, baudrate=settings.SERIAL_BAUDRATE)
    return _serial_comm


class InventoryService:
    def __init__(self, repository: InventoryRepository | None = None):
        self.repository = repository or InventoryRepository()

    async def update_on_drop(self, log_sender: LogSender, context: str = "session") -> bool:
        try:
            inventory_data = self.repository.load()
            old_quantity = inventory_data.get("current_quantity", 0)
            inventory_data["current_quantity"] = max(0, old_quantity - 1)
            inventory_data["total_dispensed"] = inventory_data.get("total_dispensed", 0) + 1
            inventory_data["last_updated"] = now_utc().isoformat()
            self.repository.save(inventory_data)

            event = "admin_condom_dispensed" if context == "admin" else "session_condom_dispensed"
            log_sender.log(event)
            log.info(
                f"{context}-condom-dispensed-successfully",
                old_quantity=old_quantity,
                new_quantity=inventory_data["current_quantity"],
                total_dispensed=inventory_data["total_dispensed"],
                timestamp=now_utc().isoformat(),
            )
            return True
        except Exception as exc:
            log.error(f"{context}-inventory-update-error", error=str(exc))
            return False

    async def update(self, data: dict, log_sender: LogSender) -> dict:
        current_data = self.repository.load()
        old_quantity = current_data.get("current_quantity", 0)
        updated_data = {
            **current_data,
            **data,
            "previous_quantity": old_quantity,
            "quantity_change": data.get("current_quantity", 0) - old_quantity,
            "last_updated": now_utc().isoformat(),
        }
        self.repository.save(updated_data)

        if "current_quantity" in data:
            log_sender.log("inventory_updated", additional=f"old:{old_quantity},new:{data['current_quantity']}")
            async with serial_lock:
                get_serial_comm().send("reset")
            log.info(
                "inventory-updated",
                old_quantity=old_quantity,
                new_quantity=data["current_quantity"],
                quantity_change=updated_data["quantity_change"],
                total_dispensed=updated_data.get("total_dispensed", 0),
                timestamp=now_utc().isoformat(),
            )
        return {"status": "inventory_updated"}


class MachineService:
    def __init__(
        self,
        session_repository: SessionRepository | None = None,
        inventory_service: InventoryService | None = None,
    ):
        self.sessions = session_repository or SessionRepository()
        self.inventory = inventory_service or InventoryService()

    async def init_qrcode(self) -> QRCodeInitResponse:
        session_id = str(uuid.uuid4())
        long_url = f"{settings.CADASTRO_BASE_URL}?sid={session_id}"
        try:
            shortener_data, short_url = await create_short_link(long_url, session_id=session_id)
        except Exception as exc:
            log.error("qrcode-init-failed", error=str(exc))
            raise HTTPException(500, "Falha ao gerar QR/link no encurtador")

        doc = {
            "_id": session_id,
            "slug": shortener_data.slug,
            "short_url": short_url,
            "status": "pending",
            "retire_sent": False,
            "processing": False,
            "created_at": now_utc(),
            "form_opened_at": None,
            "processing_started_at": None,
            "completed_at": None,
        }
        await self.sessions.create(doc)
        log.info("docile-session-created", session_id=session_id, short_url=short_url)
        return QRCodeInitResponse(
            session_id=session_id,
            short_url=short_url,
            slug=shortener_data.slug,
            qr_png=shortener_data.qr_png,
            qr_svg=shortener_data.qr_svg,
        )

    async def complete_session(self, req: SessionCompleteRequest) -> SessionCompleteResponse:
        doc = await self.sessions.try_start_processing(req.session_id, req.slug, now_utc())
        if not doc:
            session = await self.sessions.find(req.session_id)
            if not session:
                raise HTTPException(404, "Sessão inválida ou expirada")
            if session.get("slug") != req.slug:
                raise HTTPException(400, "Slug não corresponde à sessão")
            raise HTTPException(409, "Sessão já encerrada ou em processamento")

        status_final = "failed"
        log_sender = LogSender()
        try:
            log_sender.log("session_complete")
            async with serial_lock:
                serial_comm = get_serial_comm()
                udp_sender = get_udp_sender()
                serial_comm.send("drop")
                start = time.time()
                while time.time() - start < 20:
                    response = serial_comm.receive()
                    if response == "dropped":
                        udp_sender.send_with_confirmation("cta")
                        log_sender.log("product_dropped")
                        log.info("product-dropped-successfully", session_id=req.session_id)
                        await self.inventory.update_on_drop(log_sender, "session")
                        status_final = "completed"
                        break
                    if response in ["hand_timeout", "out_of_stock"]:
                        log.error("serial-error", error=response, session_id=req.session_id, slug=req.slug)
                        log_sender.log("serial_error", additional=response)
                        udp_sender.send_with_confirmation("cta")
                        break
                    await asyncio.sleep(0.1)
                else:
                    log.error("serial-timeout", session_id=req.session_id, slug=req.slug)
                    udp_sender.send_with_confirmation("cta")
            return SessionCompleteResponse(status="ok", session_id=req.session_id)
        except HTTPException:
            raise
        except Exception as exc:
            log.error("session-complete-error", error=str(exc), session_id=req.session_id, slug=req.slug)
            get_udp_sender().send_with_confirmation("cta")
            raise HTTPException(500, "Erro interno do servidor")
        finally:
            await self.sessions.finalize(req.session_id, status_final, now_utc())
            log.info("docile-session-finalized", session_id=req.session_id, status=status_final)

    async def get_session_info(self, sid: str) -> SessionGetResponse:
        session = await self.sessions.find(sid)
        if not session:
            raise HTTPException(status_code=404, detail="Sessão inválida ou expirada")
        return SessionGetResponse(
            session_id=session["_id"],
            slug=session["slug"],
            status=session["status"],
            short_url=session.get("short_url"),
            created_at=session.get("created_at"),
            form_opened_at=session.get("form_opened_at"),
            processing_started_at=session.get("processing_started_at"),
            completed_at=session.get("completed_at"),
        )

    async def open_form(self, sid: str) -> str:
        session = await self.sessions.find(sid)
        if not session:
            log.error("html-session-expired", page="form")
            return "error.html"
        if session["status"] != "pending":
            log.error("html-session-used", page="form")
            raise HTTPException(404, "Sessão Inválida.")

        updated = await self.sessions.try_mark_form_opened(sid, now_utc())
        if updated:
            log.info("form-opened-first-time", session_id=sid)
            LogSender().log("form_page_accessed")
            get_udp_sender().send("retire")
            return "form.html"

        session = await self.sessions.find(sid)
        LogSender().log("form_used_or_invalid", status=session.get("status") if session else None)
        return "used.html"

    async def turn_on(self) -> dict:
        log_sender = LogSender()
        async with serial_lock:
            serial_comm = get_serial_comm()
            udp_sender = get_udp_sender()
            serial_comm.send("on")
            start_time = time.time()
            while time.time() - start_time < 10:
                response = serial_comm.receive()
                if response == "start":
                    udp_sender.send_with_confirmation("calor")
                    log_sender.log("start_received")
                    log_sender.log("machine_started")
                    log.info("start-recebido-e-calor-enviado", timestamp=now_utc().isoformat())
                    return {"status": "start_received"}
                await asyncio.sleep(0.1)
        log.error("timeout-aguardando-start", timestamp=now_utc().isoformat())
        return {"status": "start_dont_respond"}

    async def turn_off(self) -> dict:
        async with serial_lock:
            get_serial_comm().send("off")
        LogSender().log("machine_turned_off")
        log.info("machine-turned-off", timestamp=now_utc().isoformat())
        return {"status": "machine_turned_off"}

    async def admin_dispense(self) -> dict:
        log_sender = LogSender()
        await self.inventory.update_on_drop(log_sender, "admin")
        async with serial_lock:
            get_serial_comm().send("hand")
            log_sender.log("admin_dispense_triggered")
        return {"status": "completed"}
