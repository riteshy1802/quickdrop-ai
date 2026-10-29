from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, JsonValue

TraceType = Literal["message_in", "tool_call", "decision", "reply", "error"]


class TraceEvent(BaseModel):
    at: datetime
    type: TraceType
    name: str
    input: dict[str, JsonValue] | None
    output: JsonValue


class InternalTrace(TraceEvent):
    id: UUID
    conversation_id: UUID
    rider_id: str
