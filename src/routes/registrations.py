import uuid
import structlog

from datetime import datetime, date, timedelta, timezone, time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import EmailStr
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument, ReadPreference

from schemas.user import (
    UserInitRequest,
    UserInitResponse,
    UserUpdateRequest,
    UserGetResponse,
    UserPickupRequest,
    UserPickupResponse,
)

from core.db import db

log = structlog.get_logger()
router = APIRouter(prefix="/api/users")

DEFAULT_COLLECTION = "machine"

def get_collection(collection_name: str = DEFAULT_COLLECTION):
    return db[collection_name]

def today_utc_date() -> date:
    return datetime.now(timezone.utc)

async def ensure_unique_email_index(coll):
    """Garante índice único em email"""
    try:
        await coll.create_index("email", unique=True, name="uniq_email")
    except Exception as e:
        log.warning("ensure-unique-email-index-failed", error=str(e))


@router.post("/", response_model=UserInitResponse)
async def create_user(
    payload: UserInitRequest,
    collection: str = Query(DEFAULT_COLLECTION),
):
    coll = get_collection(collection).with_options(read_preference=ReadPreference.PRIMARY)
    await ensure_unique_email_index(coll)

    reg_id = str(uuid.uuid4())
    today = today_utc_date()
    register_day = payload.registerDay or today

    doc = {
        "_id": reg_id,
        "code": payload.code,
        "name": payload.name,
        "email": str(payload.email).lower(),
        "registerDay": register_day,             # date
        "canPickFrom": register_day,             # date
        "status": "registered",                  # registered
        "createdAt": today,                      # date
        "updatedAt": today,                      # date
        "pickedDay": None,                       # date|None
        "condomsPicked": 0,                       # int
        "createdAt": today,                      # date
        "updatedAt": today,                      # date
    }

    try:
        await coll.insert_one(doc)
    except DuplicateKeyError:
        log.warning("email-already-exists", email=payload.email, collection=collection)
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")

    log.info("user-created", id=reg_id, collection=collection)

    # TODO callback with redirect
    return UserInitResponse(
        id=reg_id,
        name=doc["name"],
        email=doc["email"],
        status=doc["status"],
        registerDay=doc["registerDay"],
        canPickFrom=doc["canPickFrom"],
    )


@router.get("/", response_model=List[UserGetResponse])
async def list_users(
    collection: str = Query(DEFAULT_COLLECTION),
):
    coll = get_collection(collection)
    users = await coll.find()
    result = [
        UserGetResponse(
            id=u["_id"],
            name=u["name"],
            email=u["email"],
            status=u.get("status", "registered"),
            registerDay=u["registerDay"],
            canPickFrom=u["canPickFrom"],
            pickedDay=u.get("pickedDay"),
            condomsPicked=u.get("condomsPicked", 0),
        )
        for u in users
    ]
    log.info("users-listed", count=len(result), collection=collection)
    return result


@router.get("/{user_id}", response_model=UserGetResponse)
async def get_user(
    user_id: str,
    collection: str = Query(DEFAULT_COLLECTION),
):
    coll = get_collection(collection)
    u = await coll.find_one({"_id": user_id})
    if not u:
        log.warning("user-not-found", user_id=user_id, collection=collection)
        raise HTTPException(status_code=404, detail="Registro não encontrado")

    log.info("user-retrieved", user_id=user_id, collection=collection)
    return UserGetResponse(
        id=u["_id"],
        name=u["name"],
        email=u["email"],
        status=u.get("status", "registered"),
        registerDay=u["registerDay"],
        canPickFrom=u["canPickFrom"],
        pickedDay=u.get("pickedDay"),
        condomsPicked=u.get("condomsPicked", 0),
    )


@router.get("/email/{email}", response_model=UserGetResponse)
async def get_user_by_email(
    email: EmailStr,
    collection: str = Query(DEFAULT_COLLECTION),
):
    coll = get_collection(collection)
    u = await coll.find_one({"email": str(email).lower()})
    if not u:
        log.warning("email-not-found", email=email, collection=collection)
        raise HTTPException(status_code=404, detail="Registro não encontrado")

    log.info("user-retrieved-by-email", email=email, collection=collection)
    return UserGetResponse(
        id=u["_id"],
        name=u["name"],
        email=u["email"],
        status=u.get("status", "registered"),
        registerDay=u["registerDay"],
        canPickFrom=u["canPickFrom"],
        pickedDay=u.get("pickedDay"),
        condomsPicked=u.get("condomsPicked", 0),
    )


@router.put("/{user_id}", response_model=UserGetResponse)
async def update_user(
    user_id: str,
    update: UserUpdateRequest,
    collection: str = Query(DEFAULT_COLLECTION),
):
    coll = get_collection(collection)
    set_fields = {}
    if update.name is not None:
        set_fields["name"] = update.name
    if not set_fields:
        raise HTTPException(status_code=400, detail="Nada para atualizar")

    set_fields["updatedAt"] = datetime.now(timezone.utc)

    u = await coll.find_one_and_update(
        {"_id": user_id},
        {"$set": set_fields},
        return_document=ReturnDocument.AFTER,
    )
    if not u:
        log.warning("user-update-not-found", user_id=user_id, collection=collection)
        raise HTTPException(status_code=404, detail="Registro não encontrado")

    log.info("user-updated", user_id=user_id, collection=collection)
    return UserGetResponse(
        id=u["_id"],
        name=u["name"],
        email=u["email"],
        birthDate=u["birthDate"],
        status=u.get("status", "registered"),
        registerDay=u["registerDay"],
        canPickFrom=u["canPickFrom"],
        pickedDay=u.get("pickedDay"),
        condomsPicked=u.get("condomsPicked", 0),
    )


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    collection: str = Query(DEFAULT_COLLECTION)
):
    coll = get_collection(collection)
    result = await coll.delete_one({"_id": user_id})
    if result.deleted_count == 0:
        log.warning("user-delete-not-found", user_id=user_id, collection=collection)
        raise HTTPException(status_code=404, detail="Registro não encontrado")

    log.info("user-deleted", user_id=user_id, collection=collection)
    return {"detail": "Registro removido com sucesso"}


@router.post("/pickup", response_model=UserPickupResponse)
async def register_pickup(
    payload: UserPickupRequest = Body(...),
    collection: str = Query(DEFAULT_COLLECTION),
):
    coll = get_collection(collection)

    if not payload.id and not payload.email:
        raise HTTPException(status_code=400, detail="Informe id ou email")

    q = {"_id": payload.id} if payload.id else {"email": str(payload.email).lower()}
    u = await coll.find_one(q)
    if not u:
        log.warning("user-pickup-not-found", query=q, collection=collection)
        raise HTTPException(status_code=404, detail="Registro não encontrado")

    # --- normaliza 'day' para meia-noite UTC ---
    if not payload.day:
        # Se não vier no payload, usa hoje
        d = today_utc_date()
        day_dt = d.replace(hour=0, minute=0, second=0, microsecond=0)
    elif isinstance(payload.day, str):
        try:
            d = datetime.fromisoformat(payload.day)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Formato de 'day' inválido (use YYYY-MM-DD)"
            )
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        day_dt = d.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        if isinstance(payload.day, datetime):
            d = payload.day
        else:
            d = datetime.combine(payload.day, time.min)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        day_dt = d.replace(hour=0, minute=0, second=0, microsecond=0)

    # canPickFrom -> normaliza
    canPickFrom = u.get("canPickFrom")
    if isinstance(canPickFrom, datetime):
        cp = canPickFrom
    elif canPickFrom:
        cp = datetime.combine(canPickFrom, time.min).replace(tzinfo=timezone.utc)
    else:
        cp = day_dt  # retrocompat
    can_pick_from_dt = cp.replace(hour=0, minute=0, second=0, microsecond=0)

    # pickedDay prévio -> normaliza
    prev_pick = u.get("pickedDay")
    if isinstance(prev_pick, datetime):
        prev_picked_dt = prev_pick.replace(hour=0, minute=0, second=0, microsecond=0)
    elif prev_pick:
        prev_picked_dt = datetime.combine(prev_pick, time.min).replace(tzinfo=timezone.utc)
    else:
        prev_picked_dt = None

    # ===== Regras por DIA (usa .date() pra evitar naive vs aware) =====
    is_first_pick = prev_picked_dt is None and int(u.get("condomsPicked", 0)) == 0

    if not is_first_pick and day_dt.date() < can_pick_from_dt.date():
        raise HTTPException(
            status_code=422,
            detail=f"Só pode retirar a partir de {can_pick_from_dt.date().isoformat()}",
        )

    if prev_picked_dt is not None and prev_picked_dt.date() == day_dt.date():
        raise HTTPException(status_code=409, detail="Retirada já registrada para este dia")

    qty = int(payload.condomsPicked)
    next_can_pick_dt = (day_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Update atômico: impede 2ª retirada no mesmo dia e soma sucos
    res = await coll.update_one(
        {
            **q,
            "$or": [{"pickedDay": {"$exists": False}}, {"pickedDay": {"$ne": day_dt}}],
        },
        {
            "$inc": {"condomsPicked": qty},
            "$set": {
                "pickedDay": day_dt,
                "status": "picked",
                "canPickFrom": next_can_pick_dt,
                "updatedAt": datetime.now(timezone.utc),
            },
        },
        upsert=False,
    )

    if res.modified_count == 0:
        raise HTTPException(status_code=409, detail="Retirada já registrada para este dia")

    updated = await coll.find_one(q)

    log.info(
        "user-picked",
        id=updated["_id"],
        day=str(day_dt.date()),
        qty=int(updated.get("condomsPicked", 0)),
        next_can_pick=str(next_can_pick_dt.date()),
        collection=collection,
    )

    return {
        "id": updated["_id"],
        "email": updated["email"],
        "pickedDay": day_dt.date().isoformat(),
        "condomsPicked": int(updated.get("condomsPicked", 0)),  # total acumulado
        "status": updated.get("status", "picked"),
    }


@router.post("/eligibility/refresh")
async def refresh_eligibility(
    collection: str = Query(DEFAULT_COLLECTION),
):
    """
    Atualiza usuários de 'registered' -> 'eligible' quando hoje >= canPickFrom.
    Pode ser chamado por um cron/worker diário.
    """
    coll = get_collection(collection)
    today = today_utc_date()
    res = coll.update_many(
        {"status": "registered", "canPickFrom": {"$lte": today}},
        {"$set": {"status": "eligible", "updatedAt": datetime.now(timezone.utc)}},
    )
    log.info(
        "eligibility-refreshed",
        matched=res.matched_count,
        modified=res.modified_count,
        collection=collection
    )
    return {"matched": res.matched_count, "modified": res.modified_count}
