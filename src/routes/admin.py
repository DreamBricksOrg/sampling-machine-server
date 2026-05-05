import csv
import io
import jwt
import structlog

from datetime import datetime, timezone, date, time
from typing import Optional, Any, Dict, List

from fastapi import (
    APIRouter, Depends, HTTPException, Query, Path, status, Security
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse

from core.config import settings
from core.db import db

log = structlog.get_logger()
bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/admin")

DEFAULT_COLLECTION = "docile_elite"

def get_collection(name: str = DEFAULT_COLLECTION):
    return db[name]

def dt2date_str(x) -> str | None:
    """Converte datetime/date para 'YYYY-MM-DD'. Retorna None se vazio."""
    if not x:
        return None
    if isinstance(x, datetime):
        return x.date().isoformat()
    if isinstance(x, date):
        return x.isoformat()
    return None

def safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default

async def admin_required(
    credentials: HTTPAuthorizationCredentials = Security(bearer)
) -> Dict[str, Any]:
    """
    Aceita QUALQUER JWT válido (sem checar role). 
    Se quiser reabilitar no futuro, adicione checagem de 'role' aqui.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Credenciais ausentes")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
    return payload

@router.get("/users", dependencies=[Depends(admin_required)], response_model=Any)
async def list_users(
    name: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    collection: str = Query(DEFAULT_COLLECTION),
) -> Any:
    coll = get_collection(collection)
    filters: dict = {}

    if name:
        filters["name"] = {"$regex": name, "$options": "i"}
    if email:
        filters["email"] = {"$regex": email, "$options": "i"}

    if date_from or date_to:
        dt_filter: dict = {}
        if date_from:
            start = datetime.combine(date_from, time.min).replace(tzinfo=timezone.utc)
            dt_filter["$gte"] = start
        if date_to:
            end = datetime.combine(date_to, time.max).replace(tzinfo=timezone.utc)
            dt_filter["$lte"] = end
        filters["createdAt"] = dt_filter

    skip = (page - 1) * page_size

    cursor = (
        coll.find(filters)
            .sort("createdAt", -1)
            .skip(skip)
            .limit(page_size)
    )

    results: List[Dict[str, Any]] = []
    async for doc in cursor:
        results.append({
            "id": str(doc["_id"]),                         # UUID string
            "name": doc.get("name", ""),
            "email": doc.get("email", ""),
            "status": doc.get("status", ""),
            "birthDate": dt2date_str(doc.get("birthDate")),
            "registerDay": dt2date_str(doc.get("registerDay")),
            "canPickFrom": dt2date_str(doc.get("canPickFrom")),
            "pickedDay": dt2date_str(doc.get("pickedDay")),
            "juicesPicked": safe_int(doc.get("juicesPicked", 0)),
        })

    total = await coll.count_documents(filters)

    log.info("admin-list-users", filters=filters, page=page, page_size=page_size, collection=collection)

    return {
        "data": results,
        "page": page,
        "page_size": page_size,
        "total": total
    }

@router.get("/users/export", dependencies=[Depends(admin_required)], response_class=StreamingResponse)
async def export_users(
    name: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    collection: str = Query(DEFAULT_COLLECTION),
):
    coll = get_collection(collection)

    filters: dict = {}
    if name:
        filters["name"] = {"$regex": name, "$options": "i"}
    if email:
        filters["email"] = {"$regex": email, "$options": "i"}
    if date_from or date_to:
        dtf: dict = {}
        if date_from:
            dtf["$gte"] = datetime.combine(date_from, time.min).replace(tzinfo=timezone.utc)
        if date_to:
            dtf["$lte"] = datetime.combine(date_to, time.max).replace(tzinfo=timezone.utc)
        filters["createdAt"] = dtf

    cursor = coll.find(filters).sort("createdAt", -1)

    log.info("admin-export-users", filters=filters, collection=collection)

    async def csv_generator():
        buf = io.StringIO()
        writer = csv.writer(buf)
        # Cabeçalho (sem phone/cpf)
        writer.writerow([
            "id", "name", "email", "status",
            "birthDate", "registerDay", "canPickFrom", "pickedDay",
            "juicesPicked", "createdAt"
        ])
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)

        async for doc in cursor:
            writer.writerow([
                str(doc["_id"]),
                doc.get("name", ""),
                doc.get("email", ""),
                doc.get("status", ""),
                dt2date_str(doc.get("birthDate")) or "",
                dt2date_str(doc.get("registerDay")) or "",
                dt2date_str(doc.get("canPickFrom")) or "",
                dt2date_str(doc.get("pickedDay")) or "",
                safe_int(doc.get("juicesPicked", 0)),
                (doc.get("createdAt") or datetime.now(timezone.utc)).isoformat(),
            ])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    headers = {
        "Content-Disposition": 'attachment; filename="users.csv"',
        "Content-Type": "text/csv; charset=utf-8"
    }
    return StreamingResponse(csv_generator(), headers=headers)

@router.get("/users/{user_id}", dependencies=[Depends(admin_required)])
async def get_user(
    user_id: str = Path(..., title="ID do Usuário"),
    collection: str = Query(DEFAULT_COLLECTION),
):
    coll = get_collection(collection)

    # _id é UUID string neste projeto
    doc = await coll.find_one({"_id": user_id})
    if not doc:
        log.warning("admin-user-not-found", user_id=user_id, collection=collection)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    result = {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "email": doc.get("email", ""),
        "status": doc.get("status", ""),
        "birthDate": dt2date_str(doc.get("birthDate")),
        "registerDay": dt2date_str(doc.get("registerDay")),
        "canPickFrom": dt2date_str(doc.get("canPickFrom")),
        "pickedDay": dt2date_str(doc.get("pickedDay")),
        "juicesPicked": safe_int(doc.get("juicesPicked", 0)),
        "createdAt": (doc.get("createdAt") or datetime.now(timezone.utc)).isoformat(),
    }

    log.info("admin-get-user", user_id=user_id, collection=collection)
    return result

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(admin_required)])
async def delete_user(
    user_id: str = Path(..., description="ID do Usuário a ser excluído"),
    collection: str = Query(DEFAULT_COLLECTION),
):
    coll = get_collection(collection)
    result = await coll.delete_one({"_id": user_id})
    if result.deleted_count == 0:
        log.warning("admin-delete-failed", user_id=user_id, collection=collection)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    log.info("admin-delete-user", user_id=user_id, collection=collection)
    return
