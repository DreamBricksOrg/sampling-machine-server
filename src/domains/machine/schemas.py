from pydantic import BaseModel


class DropRequest(BaseModel):
    drop_code: str
