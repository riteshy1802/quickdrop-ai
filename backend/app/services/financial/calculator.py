"""Pure Decimal arithmetic; independent of ORM, clock and ambient decimal context."""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext

from app.services.financial.types import TripRecord

ZERO = Decimal("0")
ONE = Decimal("1")


def require_decimal(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("A finite Decimal is required")
    return value


def _context(values: Iterable[Decimal]) -> Context:
    values = tuple(require_decimal(v) for v in values)
    precision = 32 + sum(len(v.as_tuple().digits) + abs(v.as_tuple().exponent) for v in values)
    return Context(prec=max(50, precision), rounding=ROUND_HALF_UP)


def exact_sum(values: Iterable[Decimal]) -> Decimal:
    values = tuple(values)
    with localcontext(_context(values)):
        return sum(values, ZERO)


def subtract(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(_context((left, right))):
        return left - right


def round_rupees(amount: Decimal) -> Decimal:
    with localcontext(_context((amount,))):
        return amount.quantize(ONE, rounding=ROUND_HALF_UP)


def completed_trip_pay(distance_km: Decimal, surge_multiplier: Decimal) -> Decimal:
    require_decimal(distance_km)
    require_decimal(surge_multiplier)
    if distance_km < ZERO or surge_multiplier <= ZERO:
        raise ValueError("Distance must be nonnegative and surge strictly positive")
    with localcontext(_context((distance_km, surge_multiplier))):
        base = Decimal("25") + Decimal("6") * max(ZERO, distance_km - Decimal("2"))
        return round_rupees(base * surge_multiplier)


def cancellation_pay(status: str) -> Decimal:
    if status == "cancelled_by_rider":
        return Decimal("-10")
    if status == "cancelled_by_customer":
        return ZERO
    raise ValueError("Expected a cancellation status")


def trip_pay(trip: TripRecord) -> Decimal:
    if trip.status == "completed":
        return completed_trip_pay(trip.distance_km, trip.surge_multiplier)
    return cancellation_pay(trip.status)


def expected_total(trips: Iterable[TripRecord]) -> Decimal:
    """Net trip earnings/penalties; each completed trip is rounded before aggregation."""
    unique = {}
    for trip in trips:
        if unique.setdefault(trip.trip_id, trip) != trip:
            raise ValueError("Conflicting duplicate trip records")
    return exact_sum(trip_pay(trip) for trip in unique.values())
