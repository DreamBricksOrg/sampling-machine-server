import uuid
from datetime import date, datetime, time, timedelta, timezone

import structlog
from fastapi import HTTPException
from pydantic import EmailStr
from pymongo.errors import DuplicateKeyError

from .schemas import (
    UserGetResponse,
    UserInitRequest,
    UserInitResponse,
    UserPickupRequest,
    UserPickupResponse,
    UserUpdateRequest,
)
from .repositories import DEFAULT_COLLECTION, UserRepository

log = structlog.get_logger()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def start_of_day_utc(value) -> datetime:
    if not value:
        value = now_utc()
    elif isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de 'day' inválido (use YYYY-MM-DD)")
    elif isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, time.min)

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def user_response(doc: dict) -> UserGetResponse:
    return UserGetResponse(
        id=doc["_id"],
        name=doc["name"],
        email=doc["email"],
        status=doc.get("status", "registered"),
        registerDay=doc["registerDay"],
        canPickFrom=doc["canPickFrom"],
        pickedDay=doc.get("pickedDay"),
        condomsPicked=doc.get("condomsPicked", 0),
    )


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    @classmethod
    def for_collection(cls, collection: str = DEFAULT_COLLECTION) -> "UserService":
        return cls(UserRepository(collection))

    async def create_user(self, payload: UserInitRequest) -> UserInitResponse:
        repo = self.repository.primary()
        try:
            await repo.ensure_unique_email_index()
        except Exception as exc:
            log.warning("ensure-unique-email-index-failed", error=str(exc))

        reg_id = str(uuid.uuid4())
        today = now_utc()
        register_day = payload.registerDay or today
        doc = {
            "_id": reg_id,
            "code": payload.code,
            "name": payload.name,
            "email": str(payload.email).lower(),
            "registerDay": register_day,
            "canPickFrom": register_day,
            "status": "registered",
            "createdAt": today,
            "updatedAt": today,
            "pickedDay": None,
            "condomsPicked": 0,
        }

        try:
            await repo.create(doc)
        except DuplicateKeyError:
            log.warning("email-already-exists", email=payload.email, collection=repo.collection_name)
            raise HTTPException(status_code=409, detail="E-mail já cadastrado")

        log.info("user-created", id=reg_id, collection=repo.collection_name)
        return UserInitResponse(
            id=reg_id,
            name=doc["name"],
            email=doc["email"],
            status=doc["status"],
            registerDay=doc["registerDay"],
            canPickFrom=doc["canPickFrom"],
        )

    async def list_users(self) -> list[UserGetResponse]:
        users = await self.repository.list()
        result = [user_response(user) for user in users]
        log.info("users-listed", count=len(result), collection=self.repository.collection_name)
        return result

    async def get_user(self, user_id: str) -> UserGetResponse:
        user = await self.repository.find_by_id(user_id)
        if not user:
            log.warning("user-not-found", user_id=user_id, collection=self.repository.collection_name)
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        return user_response(user)

    async def get_user_by_email(self, email: EmailStr) -> UserGetResponse:
        user = await self.repository.find_by_email(str(email))
        if not user:
            log.warning("email-not-found", email=email, collection=self.repository.collection_name)
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        return user_response(user)

    async def update_user(self, user_id: str, update: UserUpdateRequest) -> UserGetResponse:
        fields = {}
        if update.name is not None:
            fields["name"] = update.name
        if not fields:
            raise HTTPException(status_code=400, detail="Nada para atualizar")

        fields["updatedAt"] = now_utc()
        user = await self.repository.update_name(user_id, fields)
        if not user:
            log.warning("user-update-not-found", user_id=user_id, collection=self.repository.collection_name)
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        return user_response(user)

    async def delete_user(self, user_id: str) -> dict:
        deleted = await self.repository.delete(user_id)
        if deleted == 0:
            log.warning("user-delete-not-found", user_id=user_id, collection=self.repository.collection_name)
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        return {"detail": "Registro removido com sucesso"}

    async def register_pickup(self, payload: UserPickupRequest) -> UserPickupResponse:
        if not payload.id and not payload.email:
            raise HTTPException(status_code=400, detail="Informe id ou email")

        query = {"_id": payload.id} if payload.id else {"email": str(payload.email).lower()}
        user = await self.repository.find_one(query)
        if not user:
            log.warning("user-pickup-not-found", query=query, collection=self.repository.collection_name)
            raise HTTPException(status_code=404, detail="Registro não encontrado")

        day_dt = start_of_day_utc(payload.day)
        can_pick_from_dt = start_of_day_utc(user.get("canPickFrom") or day_dt)
        prev_pick = user.get("pickedDay")
        prev_picked_dt = start_of_day_utc(prev_pick) if prev_pick else None
        is_first_pick = prev_picked_dt is None and int(user.get("condomsPicked", 0)) == 0

        if not is_first_pick and day_dt.date() < can_pick_from_dt.date():
            raise HTTPException(
                status_code=422,
                detail=f"Só pode retirar a partir de {can_pick_from_dt.date().isoformat()}",
            )
        if prev_picked_dt is not None and prev_picked_dt.date() == day_dt.date():
            raise HTTPException(status_code=409, detail="Retirada já registrada para este dia")

        next_can_pick_dt = start_of_day_utc(day_dt + timedelta(days=1))
        modified = await self.repository.register_pickup(
            query,
            day_dt,
            int(payload.condomsPicked),
            next_can_pick_dt,
            now_utc(),
        )
        if modified == 0:
            raise HTTPException(status_code=409, detail="Retirada já registrada para este dia")

        updated = await self.repository.find_one(query)
        log.info(
            "user-picked",
            id=updated["_id"],
            day=str(day_dt.date()),
            qty=int(updated.get("condomsPicked", 0)),
            next_can_pick=str(next_can_pick_dt.date()),
            collection=self.repository.collection_name,
        )
        return UserPickupResponse(
            id=updated["_id"],
            email=updated["email"],
            pickedDay=day_dt,
            condomsPicked=int(updated.get("condomsPicked", 0)),
            status=updated.get("status", "picked"),
        )

    async def refresh_eligibility(self) -> dict:
        result = await self.repository.refresh_eligibility(now_utc(), now_utc())
        log.info(
            "eligibility-refreshed",
            matched=result.matched_count,
            modified=result.modified_count,
            collection=self.repository.collection_name,
        )
        return {"matched": result.matched_count, "modified": result.modified_count}
