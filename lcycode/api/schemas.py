from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    auto_continue: Optional[bool] = None  # overrides key.json's routing.auto_continue for this run


class ContinueRequest(BaseModel):
    session_id: str
    auto_continue: Optional[bool] = None


class CancelRequest(BaseModel):
    session_id: str
