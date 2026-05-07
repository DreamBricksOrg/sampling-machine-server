import json
from pathlib import Path

from pymongo import ReturnDocument

from infrastructure.database.mongo import db

SESSIONS_COLLECTION = "docile_sessions"
BASE_DIR = Path(__file__).resolve().parents[2]
INVENTORY_FILE = BASE_DIR / "static" / "docile" / "assets" / "inventory.json"


class SessionRepository:
    def __init__(self):
        self.collection = db[SESSIONS_COLLECTION]

    async def create(self, doc: dict) -> None:
        await self.collection.insert_one(doc)

    async def find(self, session_id: str) -> dict | None:
        return await self.collection.find_one({"_id": session_id})

    async def try_mark_form_opened(self, session_id: str, now):
        return await self.collection.find_one_and_update(
            {
                "_id": session_id,
                "status": "pending",
                "retire_sent": {"$ne": True},
            },
            {
                "$set": {
                    "retire_sent": True,
                    "status": "form_shown",
                    "form_opened_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    async def try_start_processing(self, session_id: str, slug: str, now):
        return await self.collection.find_one_and_update(
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
                    "processing_started_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    async def finalize(self, session_id: str, status: str, now) -> None:
        await self.collection.update_one(
            {"_id": session_id},
            {
                "$set": {
                    "status": status,
                    "processing": False,
                    "completed_at": now,
                }
            },
        )


class InventoryRepository:
    def __init__(self, file_path: Path = INVENTORY_FILE):
        self.file_path = file_path

    def load(self) -> dict:
        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def save(self, data: dict) -> None:
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
