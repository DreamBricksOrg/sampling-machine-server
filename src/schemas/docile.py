from typing import Optional, Literal
from pydantic import BaseModel, AnyUrl, HttpUrl
from datetime import datetime

class QRCodeInitResponse(BaseModel):
    session_id: str
    short_url: HttpUrl
    slug: str
    qr_png: HttpUrl
    qr_svg: HttpUrl

class SessionCompleteRequest(BaseModel):
    session_id: str
    slug: str

class SessionCompleteResponse(BaseModel):
    status: str
    session_id: str

class SessionGetResponse(BaseModel):
    session_id: str
    slug: str
    status: Literal["pending", "form_shown", "processing", "completed", "failed", "aborted"]
    short_url: Optional[AnyUrl] = None
    created_at: datetime
    form_opened_at: Optional[datetime] = None
    processing_started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None