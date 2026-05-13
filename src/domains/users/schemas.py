from pydantic import BaseModel, EmailStr, Field, AnyUrl, HttpUrl
from typing import Optional, Literal
from datetime import datetime


Status = Literal["registered", "picked"]


# ---------- Session ----------
class SessionCompleteRequest(BaseModel):
    session_id: str
    slug: str


class SessionCompleteResponse(BaseModel):
    status: str
    session_id: str


class QRCodeInitResponse(BaseModel):
    session_id: str
    short_url: HttpUrl
    slug: str
    qr_png: HttpUrl
    qr_svg: HttpUrl


class SessionGetResponse(BaseModel):
    session_id: str
    slug: str
    status: Literal["pending", "form_shown", "processing", "completed", "failed", "aborted"]
    short_url: Optional[AnyUrl] = None
    created_at: datetime
    form_opened_at: Optional[datetime] = None
    processing_started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


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
    productsPicked: int = Field(..., ge=1, description="Quantidade retirada nesse dia")


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
    productsPicked: int = 0

class UserPickupResponse(BaseModel):
    id: str
    email: EmailStr
    pickedDay: datetime
    productsPicked: int
    status: Status  # deve vir "picked"