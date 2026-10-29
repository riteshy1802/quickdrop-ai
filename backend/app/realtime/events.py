"""Explicit public event data; no arbitrary trace or model output on rider channels."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "agent.started",
    "agent.status",
    "agent.message.delta",
    "agent.message.completed",
    "agent.completed",
    "agent.failed",
    "message.created",
    "conversation.updated",
    "conversation.takeover",
    "conversation.handoff",
    "dispute.updated",
    "ops.case.created",
    "ops.case.updated",
    "payment.status_changed",
    "payment.reconciled",
]


class EventData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str | None = None
    message_id: UUID | None = None
    text: str | None = None
    sender: Literal["AI", "RIDER", "OPS"] | None = None
    dispute_id: UUID | None = None
    case_id: UUID | None = None
    payment_id: UUID | None = None
    control_version: int | None = None


class LiveEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    conversation_id: UUID
    rider_id: str
    run_id: UUID = Field(default_factory=uuid4)
    sequence: int = Field(default=1, ge=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: EventData

    def sse(self):
        payload = self.model_dump_json(exclude_none=True)
        return f"id: {self.event_id}\nevent: {self.event_type}\ndata: {payload}\n\n"
