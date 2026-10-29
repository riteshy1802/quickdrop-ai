"""Attest requested source coverage against the immutable, approved CSV snapshot."""

from functools import lru_cache

from app.data_quality.normalize import normalize_sources, prepare_trip
from app.repositories import financial
from app.repositories.trips import IST
from app.scripts.seed import DEFAULT_DATA_DIR
from app.services.financial.types import PayoutRecord, TripRecord


@lru_cache(maxsize=2)
def canonical_snapshot(signature):
    bundle = normalize_sources(DEFAULT_DATA_DIR)
    return (
        tuple(TripRecord.model_validate(row) for row in bundle.rows["trips"]),
        tuple(PayoutRecord.model_validate(row) for row in bundle.rows["payout_lines"]),
    )


async def source_coverage(session, request):
    try:
        signature = tuple(
            (DEFAULT_DATA_DIR / filename).stat().st_mtime_ns
            for filename in ("riders.csv", "trips.csv", "payout_lines.csv")
        )
        expected_trips, expected_payouts = canonical_snapshot(signature)
    except (OSError, ValueError):
        return False
    explicit = await financial.trips_for_scope(session, request.rider_id, request.trip_ids, [])
    if len(explicit) != len(set(request.trip_ids)) or any(
        t.rider_id != request.rider_id for t in explicit
    ):
        return False
    days = sorted(
        set(request.trip_dates + request.penalty_dates + request.incentive_dates)
        | {t.started_at.astimezone(IST).date() for t in explicit}
    )
    if not days:
        return False
    trips = await financial.trips_for_scope(session, request.rider_id, (), days)
    ids = {t.trip_id for t in trips}
    payouts = await financial.payouts_for_scope(session, request.rider_id, tuple(ids), days)

    def trip_values(rows):
        return {trip.trip_id: prepare_trip(TripRecord.model_validate(trip))[0] for trip in rows}

    wanted_trips = [
        trip
        for trip in expected_trips
        if trip.rider_id == request.rider_id and trip.started_at.astimezone(IST).date() in days
    ]
    wanted_payouts = [
        p
        for p in expected_payouts
        if p.rider_id == request.rider_id and (p.payout_date in days or p.trip_id in ids)
    ]
    return trip_values(trips) == trip_values(wanted_trips) and {
        p.line_id: PayoutRecord.model_validate(p) for p in payouts
    } == {p.line_id: p for p in wanted_payouts}
