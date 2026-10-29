from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from app.repositories.trips import IST
from app.services.financial.types import TripRecord


def completed_trip_count(trips: Iterable[TripRecord], rider_id: str, day: date) -> int:
    seen = {}
    for trip in trips:
        previous = seen.setdefault(trip.trip_id, trip)
        if previous != trip:
            raise ValueError("Conflicting duplicate trip records")
    return sum(
        trip.rider_id == rider_id
        and trip.status == "completed"
        and trip.started_at.astimezone(IST).date() == day
        for trip in seen.values()
    )


def qualifies_for_incentive(completed_count: int) -> bool:
    if (
        not isinstance(completed_count, int)
        or isinstance(completed_count, bool)
        or completed_count < 0
    ):
        raise ValueError("Completed count must be a nonnegative integer")
    return completed_count >= 12


def expected_incentive(completed_count: int) -> Decimal:
    return Decimal("150") if qualifies_for_incentive(completed_count) else Decimal("0")
