from datetime import date, datetime

from app.data_quality.rules import DISTANCE_REVIEW_THRESHOLD_KM as DISTANCE_REVIEW_THRESHOLD_KM
from app.repositories.trips import IST
from app.services.financial.types import EligibilityOutcome, TripRecord


def date_eligibility(service_date: date, received_at: datetime) -> EligibilityOutcome:
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError("received_at must be timezone-aware")
    age = (received_at.astimezone(IST).date() - service_date).days
    if not 1 <= age <= 7:
        return EligibilityOutcome(
            eligible=False,
            reasons=("Claim must concern one of the seven completed IST dates before received_at",),
        )
    return EligibilityOutcome(eligible=True, reasons=("Claim is within the seven-day IST window",))


def trip_eligibility(
    rider_id: str,
    rider_exists: bool,
    trip: TripRecord | None,
    received_at: datetime,
) -> EligibilityOutcome:
    if not rider_exists:
        return EligibilityOutcome(eligible=False, reasons=("Trusted rider account was not found",))
    if trip is None:
        return EligibilityOutcome(eligible=False, reasons=("Referenced trip was not found",))
    if trip.rider_id != rider_id:
        return EligibilityOutcome(
            eligible=False, reasons=("Trip does not belong to the trusted rider",)
        )
    window = date_eligibility(trip.started_at.astimezone(IST).date(), received_at)
    return EligibilityOutcome(
        eligible=window.eligible, reasons=("Trip belongs to the trusted rider",) + window.reasons
    )


# Data-quality screen only, not a fare cap or an official policy limit.
# Values above this threshold need source-unit verification; never divide by 1000 automatically.
def distance_requires_review(trip: TripRecord) -> bool:
    return trip.status == "completed" and trip.distance_km > DISTANCE_REVIEW_THRESHOLD_KM
