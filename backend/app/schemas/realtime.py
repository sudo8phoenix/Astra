from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

WebSocketEventType = Literal[
    "connection.accepted",
    "connection.closed",
    "chat.message",
    "task.updated",
    "calendar.updated",
    "email.updated",
    "agent.status",
    "approval.required",
    "approval.resolved",
    "heartbeat",
    "error",
]


class WebSocketEvent(BaseModel):
    event: WebSocketEventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict
    trace_id: str | None = None
