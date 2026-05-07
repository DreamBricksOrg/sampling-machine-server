from pymongo import ReadPreference, ReturnDocument

from infrastructure.database.mongo import db

DEFAULT_COLLECTION = "machine"


class UserRepository:
    def __init__(self, collection_name: str = DEFAULT_COLLECTION):
        self.collection_name = collection_name
        self.collection = db[collection_name]

    def primary(self) -> "UserRepository":
        repo = UserRepository(self.collection_name)
        repo.collection = self.collection.with_options(read_preference=ReadPreference.PRIMARY)
        return repo

    async def ensure_unique_email_index(self) -> None:
        await self.collection.create_index("email", unique=True, name="uniq_email")

    async def create(self, doc: dict) -> None:
        await self.collection.insert_one(doc)

    async def list(self) -> list[dict]:
        return [doc async for doc in self.collection.find()]

    async def find_by_id(self, user_id: str) -> dict | None:
        return await self.collection.find_one({"_id": user_id})

    async def find_by_email(self, email: str) -> dict | None:
        return await self.collection.find_one({"email": email.lower()})

    async def find_one(self, query: dict) -> dict | None:
        return await self.collection.find_one(query)

    async def update_name(self, user_id: str, fields: dict) -> dict | None:
        return await self.collection.find_one_and_update(
            {"_id": user_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )

    async def delete(self, user_id: str) -> int:
        result = await self.collection.delete_one({"_id": user_id})
        return result.deleted_count

    async def register_pickup(self, query: dict, day_dt, qty: int, next_can_pick_dt, updated_at) -> int:
        result = await self.collection.update_one(
            {
                **query,
                "$or": [{"pickedDay": {"$exists": False}}, {"pickedDay": {"$ne": day_dt}}],
            },
            {
                "$inc": {"condomsPicked": qty},
                "$set": {
                    "pickedDay": day_dt,
                    "status": "picked",
                    "canPickFrom": next_can_pick_dt,
                    "updatedAt": updated_at,
                },
            },
            upsert=False,
        )
        return result.modified_count

    async def refresh_eligibility(self, today, updated_at):
        return await self.collection.update_many(
            {"status": "registered", "canPickFrom": {"$lte": today}},
            {"$set": {"status": "eligible", "updatedAt": updated_at}},
        )
