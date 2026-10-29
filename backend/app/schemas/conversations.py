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
    status: ConversationStatus | Literal["PAYMENT_VERIFICATION_REQUIRED"]
    source_status: ConversationStatus
    handler: Literal["AI", "OPS"]
    handling_mode: HandlingMode
    created_at: datetime
    updated_at: datetime
    last_message: str
    scenario: None = None
    assigned_operator_id: UUID | None = None
    control_version: int = 0


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    sender: Literal["RIDER", "AI", "OPS"]
    text: str
    created_at: datetime
    received_at: datetime | None
    visibility: Literal["RIDER", "INTERNAL"]
    operator_id: UUID | None = None
    client_message_id: str | None = None


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
