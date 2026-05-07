from typing import List

from fastapi import APIRouter, Body, Query
from pydantic import EmailStr

from .schemas import (
    UserGetResponse,
    UserInitRequest,
    UserInitResponse,
    UserPickupRequest,
    UserPickupResponse,
    UserUpdateRequest,
)
from .repositories import DEFAULT_COLLECTION
from .services import UserService

router = APIRouter(prefix="/api/users")


def service_for(collection: str) -> UserService:
    return UserService.for_collection(collection)


@router.post("/", response_model=UserInitResponse)
async def create_user(payload: UserInitRequest, collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).create_user(payload)


@router.get("/", response_model=List[UserGetResponse])
async def list_users(collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).list_users()


@router.get("/email/{email}", response_model=UserGetResponse)
async def get_user_by_email(email: EmailStr, collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).get_user_by_email(email)


@router.get("/{user_id}", response_model=UserGetResponse)
async def get_user(user_id: str, collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).get_user(user_id)


@router.put("/{user_id}", response_model=UserGetResponse)
async def update_user(user_id: str, update: UserUpdateRequest, collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).update_user(user_id, update)


@router.delete("/{user_id}")
async def delete_user(user_id: str, collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).delete_user(user_id)


@router.post("/pickup", response_model=UserPickupResponse)
async def register_pickup(payload: UserPickupRequest = Body(...), collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).register_pickup(payload)


@router.post("/eligibility/refresh")
async def refresh_eligibility(collection: str = Query(DEFAULT_COLLECTION)):
    return await service_for(collection).refresh_eligibility()
