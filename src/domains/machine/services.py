import asyncio
import time
from datetime import datetime, timezone

import structlog
from infrastructure.config import settings
from integrations.logcenter.log_sender import LogSender
from infrastructure.hardware.serial_comm import SerialComm
from infrastructure.hardware.udp_sender import UDPSender
from .repositories import InventoryRepository

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

    async def update_on_drop(self) -> bool:
        try:
            inventory_data = self.repository.load()
            old_quantity = inventory_data.get("current_quantity", 0)
            inventory_data["current_quantity"] = max(0, old_quantity - 1)
            inventory_data["total_dispensed"] = inventory_data.get("total_dispensed", 0) + 1
            inventory_data["last_updated"] = now_utc().isoformat()
            self.repository.save(inventory_data)
            log.info(
                "inventory-dispensed",
                old_quantity=old_quantity,
                new_quantity=inventory_data["current_quantity"],
                total_dispensed=inventory_data["total_dispensed"],
            )
            return True
        except Exception as exc:
            log.error("inventory-update-error", error=str(exc))
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
            )
        return {"status": "inventory_updated"}


class MachineService:
    def __init__(
        self,
        inventory_service: InventoryService | None = None,
    ):
        self.inventory = inventory_service or InventoryService()

    async def drop(self) -> None:
        async with serial_lock:
            get_serial_comm().send("drop")
        log.info("drop-sent")

    async def drop_waiting_callback(self, slug: str = "") -> str:
        log_sender = LogSender()
        async with serial_lock:
            serial_comm = get_serial_comm()
            udp_sender = get_udp_sender()
            serial_comm.send("drop")
            start = time.time()
            while time.time() - start < 20:
                response = serial_comm.receive()
                if response == "dropped":
                    log_sender.log("product_dropped")
                    log.info("product-dropped", slug=slug)
                    await self.inventory.update_on_drop()
                    udp_sender.send_with_confirmation("next")
                    return "completed"
                if response in ["hand_timeout", "out_of_stock"]:
                    log_sender.log("serial_error", additional=response)
                    log.error("serial-error", error=response, slug=slug)
                    udp_sender.send_with_confirmation("error")
                    return "failed"
                await asyncio.sleep(0.1)
        log_sender.log("serial_timeout")
        log.error("serial-timeout", slug=slug)
        udp_sender.send_with_confirmation("timeout")
        return "failed"

    async def admin_dispense(self) -> dict:
        async with serial_lock:
            get_serial_comm().send("admin_dispense")
        await self.inventory.update_on_drop()
        LogSender().log("admin_dispense_triggered")
        log.info("admin-dispensed")
        return {"status": "admin_dispense"}

    async def turn_on(self) -> dict:
        log_sender = LogSender()
        async with serial_lock:
            serial_comm = get_serial_comm()
            udp_sender = get_udp_sender()
            serial_comm.send("on")
            start_time = time.time()
            while time.time() - start_time < 10:
                response = serial_comm.receive()
                if response == "on":
                    udp_sender.send_with_confirmation("machine_on")
                    log_sender.log("machine_started")
                    log.info("machine-on")
                    return {"status": "machine_on"}
                await asyncio.sleep(0.1)
        log.error("machine-on-timeout")
        return {"status": "machine_dont_respond"}

    async def turn_off(self) -> dict:
        async with serial_lock:
            get_serial_comm().send("off")
        LogSender().log("machine_turned_off")
        log.info("machine-off")
        return {"status": "machine_turned_off"}

 
