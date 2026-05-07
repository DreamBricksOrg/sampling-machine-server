from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import StreamingResponse

from .repositories import DEFAULT_COLLECTION
from .security import admin_required
from .services import AdminUserService

router = APIRouter(prefix="/api/admin")


def service_for(collection: str) -> AdminUserService:
    return AdminUserService.for_collection(collection)


@router.get("/users", dependencies=[Depends(admin_required)], response_model=Any)
async def list_users(
    name: str | None = Query(None),
    email: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    collection: str = Query(DEFAULT_COLLECTION),
) -> Any:
    return await service_for(collection).list_users(name, email, date_from, date_to, page, page_size)


@router.get("/users/export", dependencies=[Depends(admin_required)], response_class=StreamingResponse)
async def export_users(
    name: str | None = Query(None),
    email: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    collection: str = Query(DEFAULT_COLLECTION),
):
    headers = {
        "Content-Disposition": 'attachment; filename="users.csv"',
        "Content-Type": "text/csv; charset=utf-8",
    }
    return StreamingResponse(
        service_for(collection).export_users_csv(name, email, date_from, date_to),
        headers=headers,
    )


@router.get("/users/{user_id}", dependencies=[Depends(admin_required)])
async def get_user(user_id: str = Path(..., title="ID do Usuário"), collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).get_user(user_id)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(admin_required)])
async def delete_user(user_id: str = Path(..., description="ID do Usuário a ser excluído"), collection: str = Query(DEFAULT_COLLECTION)):
    await service_for(collection).delete_user(user_id)
