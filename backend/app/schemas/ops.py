from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, PlainSerializer

# Official contract requires a JSON number. Internal money retains exact Decimal strings.
RupeesNumber = Annotated[
    Decimal,
    PlainSerializer(
        lambda value: int(value) if value == value.to_integral() else float(value),
        return_type=int | float,
        when_used="json",
    ),
]
QueueStatus = Literal["PENDING", "IN_REVIEW", "APPROVED", "REJECTED", "RESOLVED"]
PaymentStatus = Literal[
    "PENDING", "AWAITING_APPROVAL", "PROCESSING", "UNKNOWN", "SUCCEEDED", "FAILED", "NEEDS_REVIEW"
]


class PendingItem(BaseModel):
    id: UUID
    rider_id: str
    type: Literal["approval", "escalation"]
    amount: RupeesNumber | None
    reason: str
    created_at: datetime


class CaseResponse(PendingItem):
    dispute_id: UUID
    conversation_id: UUID
    status: QueueStatus
    claimed_amount: Decimal | None
    verified_amount: Decimal | None
    resolved_at: datetime | None
    assigned_to: UUID | None = None
    decision_note: str | None = None


class PayoutResponse(BaseModel):
    id: UUID
    dispute_id: UUID
    rider_id: str
    conversation_id: UUID
    amount_rupees: Decimal
    status: PaymentStatus
    initiation: Literal["AUTO", "HUMAN_APPROVED"]
    provider_id: str | None
    reconciled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OverviewResponse(BaseModel):
    total_disputes: int
    pending_approvals: int
    open_escalations: int
    human_conversations: int
    confirmed_payment_amount: Decimal
    payment_exceptions: int
