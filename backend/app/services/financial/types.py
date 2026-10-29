from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

from app.data_quality.report import Classification, DataQualityIssue, TripQuality
from app.data_quality.report import DataQualityTransformation as DataQualityTransformation
from app.schemas.trip import TripStatus


def reject_float(value):
    if isinstance(value, (float, bool)):
        raise ValueError("Use Decimal, integer, or an exact decimal string, never float")
    return value


Money = Annotated[Decimal, BeforeValidator(reject_float), Field(allow_inf_nan=False)]
SourceType = Literal["trip", "penalty", "incentive"]
ItemStatus = Literal[
    "VERIFIED",
    "NO_SHORTFALL",
    "INELIGIBLE",
    "NEEDS_INFORMATION",
    "NEEDS_RECONCILIATION",
    "REQUIRES_REVIEW",
]


class FinancialModel(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True, extra="forbid")


class ClaimRequest(FinancialModel):
    # This identity must come from a trusted caller, never from chat text or an LLM.
    rider_id: str = Field(min_length=1)
    received_at: AwareDatetime
    trip_ids: tuple[str, ...] = ()
    trip_dates: tuple[date, ...] = ()
    penalty_dates: tuple[date, ...] = ()
    incentive_dates: tuple[date, ...] = ()


class TripRecord(FinancialModel):
    trip_id: str
    rider_id: str
    started_at: AwareDatetime
    status: TripStatus
    distance_km: Annotated[Money, Field(ge=0)]
    surge_multiplier: Annotated[Money, Field(gt=0)]


class PayoutRecord(FinancialModel):
    line_id: str
    rider_id: str
    trip_id: str | None
    payout_date: date
    line_type: Literal["trip", "daily_incentive", "cancellation_penalty"]
    amount: Money


class SourceKey(FinancialModel):
    source_type: SourceType
    source_id: str
    service_date: date


class PriorItem(FinancialModel):
    source_type: SourceType
    source_id: str


class PriorIntent(FinancialModel):
    id: UUID
    status: str
    amount: Money
    provider_payout_id: str | None = None


class PriorClaim(FinancialModel):
    id: UUID
    status: str
    items: tuple[PriorItem, ...] = ()
    intents: tuple[PriorIntent, ...] = ()


class FinancialSnapshot(FinancialModel):
    rider_exists: bool
    # An ingestion-aware caller must attest coverage; absence of lines alone is not proof.
    source_data_complete: bool
    trips: tuple[TripRecord, ...] = ()
    payouts: tuple[PayoutRecord, ...] = ()
    prior_claims: tuple[PriorClaim, ...] = ()
    trip_quality: tuple[TripQuality, ...] = ()


class Allocation(SourceKey):
    amount: Annotated[Money, Field(gt=0)]


class ConfirmedPayment(FinancialModel):
    """Trusted, provider-confirmed evidence supplied by the future payment layer."""

    provider_payout_id: str = Field(min_length=1)
    intent_id: UUID | None = None
    amount: Annotated[Money, Field(gt=0)]
    allocations: tuple[Allocation, ...]

    @model_validator(mode="after")
    def allocation_total(self):
        from app.services.financial.calculator import exact_sum

        if exact_sum(a.amount for a in self.allocations) != self.amount:
            raise ValueError("Allocations must account for the entire confirmed payment")
        return self


class PaymentEvidence(FinancialModel):
    rider_id: str | None = None
    # False by default: no provider call is made in this milestone.
    provider_history_complete: bool = False
    confirmed: tuple[ConfirmedPayment, ...] = ()

    @model_validator(mode="after")
    def require_rider_scope(self):
        if (self.provider_history_complete or self.confirmed) and not self.rider_id:
            raise ValueError("Provider evidence must explicitly identify the trusted rider")
        return self


class EligibilityOutcome(FinancialModel):
    eligible: bool
    reasons: tuple[str, ...]


class ReconciledItem(SourceKey):
    service_date: date | None = None
    data_quality: Classification = "VALID"
    data_quality_issues: tuple[DataQualityIssue, ...] = ()
    eligible: bool
    status: ItemStatus
    expected_amount: Money | None = None
    historical_paid: Money | None = None
    raw_difference: Money | None = None
    verified_shortfall: Money = Decimal("0")
    confirmed_adjustments: Money = Decimal("0")
    outstanding: Money | None = None
    historical_line_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...]
    blocking_claim_ids: tuple[UUID, ...] = ()
    blocking_intent_ids: tuple[UUID, ...] = ()


class ReconciliationResult(FinancialModel):
    rider_id: str
    received_at: AwareDatetime
    eligible: bool
    status: Literal[
        "VERIFIED",
        "NO_SHORTFALL",
        "NEEDS_INFORMATION",
        "INELIGIBLE",
        "PARTIALLY_ELIGIBLE",
        "REQUIRES_REVIEW",
        "NEEDS_RECONCILIATION",
    ]
    items: tuple[ReconciledItem, ...]
    data_quality_transformations: tuple[DataQualityTransformation, ...] = ()
    expected_amount: Money
    historical_paid: Money
    raw_difference: Money
    verified_shortfall: Money
    confirmed_adjustments: Money
    outstanding: Money | None
    requires_payment_reconciliation: bool
    reasons: tuple[str, ...]
    # This engine never authorizes a transfer, even if all evidence is complete.
    payment_authorized: Literal[False] = False
