from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal
from datetime import datetime


Status = Literal["registered", "picked"]


# ---------- Requests ----------
class UserInitRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    code: str
    registerDay: Optional[datetime] = None


class UserUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1)

class UserPickupRequest(BaseModel):
    """Usado pelo worker ou endpoint para registrar a retirada de sucos."""
    id: Optional[str] = None
    email: Optional[EmailStr] = None
    day: datetime = Field(..., description="Dia da retirada")
    condomsPicked: int = Field(..., ge=1, description="Quantidade retirada nesse dia")


# ---------- Responses ----------
class UserInitResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    status: Status
    registerDay: datetime
    canPickFrom: datetime


class UserGetResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    status: Status
    registerDay: datetime
    canPickFrom: datetime
    pickedDay: Optional[datetime] = None
    condomsPicked: int = 0

class UserPickupResponse(BaseModel):
    id: str
    email: EmailStr
    pickedDay: datetime
    condomsPicked: int
    status: Status  # deve vir "picked"