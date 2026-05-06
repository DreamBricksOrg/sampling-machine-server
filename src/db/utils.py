from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings

_client: AsyncIOMotorClient | None = None

async def get_db():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URI)
    return _client[settings.MONGO_DB]