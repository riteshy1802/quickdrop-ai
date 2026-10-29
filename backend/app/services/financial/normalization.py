"""Compatibility entry point; normalization rules are owned by app.data_quality."""

from app.data_quality.rules import RULE_ID as RULE_ID
from app.data_quality.rules import trip_correction
from app.services.financial.types import DataQualityTransformation, TripRecord


def normalize_trip_record(trip: TripRecord) -> tuple[TripRecord, DataQualityTransformation | None]:
    from app.data_quality.normalize import prepare_trip

    if trip_correction(trip.model_dump()) is None:
        return trip, None
    effective, quality = prepare_trip(trip)
    return effective, quality.transformations[0]
