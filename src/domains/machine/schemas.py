from pydantic import BaseModel, Field


class DropRequest(BaseModel):
    drop_code: str


class SerialMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Mensagem enviada para a serial")
    timeout_seconds: float = Field(10, gt=0, le=60, description="Tempo máximo aguardando resposta")
