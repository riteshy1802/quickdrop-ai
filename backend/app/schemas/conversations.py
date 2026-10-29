from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ConversationStatus = Literal[
    "OPEN",
    "AWAITING_INFORMATION",
    "AWAITING_APPROVAL",
    "ESCALATED",
    "HUMAN_HANDLING",
    "PAYMENT_PENDING",
    "RESOLVED",
]
HandlingMode = Literal["AI", "HUMAN"]


class ConversationResponse(BaseModel):
    id: UUID
    rider_id: str
    title: str
    status: Literal["OPEN", "RESOLVED", "HUMAN_HANDLING", "AWAITING_APPROVAL", "PAYMENT_PENDING"]
    source_status: ConversationStatus
    handler: Literal["AI", "OPS"]
    handling_mode: HandlingMode
    created_at: datetime
    updated_at: datetime
    last_message: str
    scenario: None = None


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    sender: Literal["RIDER", "AI", "OPS"]
    text: str
    created_at: datetime
    received_at: datetime | None
    visibility: Literal["RIDER", "INTERNAL"]


class DisputeItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_type: str
    source_id: str
    expected_amount: Decimal
    actual_amount: Decimal
    difference: Decimal


class DisputeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    conversation_id: UUID
    rider_id: str
    status: str
    claimed_amount: Decimal | None
    verified_amount: Decimal | None
    created_at: datetime
    updated_at: datetime
    items: list[DisputeItemResponse] = Field(default_factory=list)
