from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class AuthorizationResult:
    status: Literal["AUTHORIZED", "EXISTING", "APPROVAL_REQUIRED", "ESCALATED", "BLOCKED"]
    reason: str
    intent_id: UUID | None = None
    queue_id: UUID | None = None


@dataclass(frozen=True)
class PaymentJob:
    id: UUID
    rider_id: str
    conversation_id: UUID
    dispute_id: UUID
    amount: Decimal
    idempotency_key: str
    reference: str
    token: UUID
    operation: Literal["POST", "RECONCILE"]
    attempt: int
    original_status: str
    never_sent: bool
    provider_id: str | None = None
    auto_pay_date: date | None = None
    payment_type: str = "OPS_APPROVED"


@dataclass(frozen=True)
class ReconcileOutcome:
    kind: Literal["CONFIRMED", "MISSING", "CONFLICT", "UNAVAILABLE"]
    code: str
    payout_id: str | None = None
    at: datetime | None = None
