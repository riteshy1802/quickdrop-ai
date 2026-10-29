"""Explicit approved rules. Thresholds identify review cases, never imply conversions."""

from datetime import UTC, datetime
from decimal import Decimal

APPROVED_RIDER_ALIASES = {"R7": "R007", "r19": "R019"}
DISTANCE_REVIEW_THRESHOLD_KM = Decimal("100")
RULE_ID = "T312538_VERIFIED_METRES_TO_KM_V1"
FINGERPRINT = {
    "trip_id": "T312538",
    "rider_id": "R031",
    "started_at": datetime(2026, 9, 18, 4, 47, tzinfo=UTC),
    "status": "completed",
    "surge_multiplier": Decimal("1.5"),
}


class NormalizationError(ValueError):
    pass


def canonical_rider_reference(rider_id: str, rider_ids: set[str]) -> str:
    if rider_id in APPROVED_RIDER_ALIASES:
        target = APPROVED_RIDER_ALIASES[rider_id]
        if target not in rider_ids or rider_id in rider_ids:
            raise NormalizationError(
                f"Rider reference {rider_id!r} is ambiguous or its canonical "
                f"rider {target!r} is missing from riders.csv"
            )
        return target
    if rider_id not in rider_ids:
        raise NormalizationError(
            f"Unknown rider reference {rider_id!r}; no approved mapping exists"
        )
    return rider_id


def approved_trip_fingerprint(values: dict) -> bool:
    return all(values.get(key) == value for key, value in FINGERPRINT.items())


def trip_correction(values: dict, *, include_canonical: bool = False) -> dict | None:
    raw = values.get("distance_km")
    if not approved_trip_fingerprint(values) or raw not in (
        (Decimal("5000"), Decimal("5")) if include_canonical else (Decimal("5000"),)
    ):
        return None
    return dict(
        rule_id=RULE_ID,
        source_file="trips.csv",
        source_id="T312538",
        field="distance_km",
        original_value="5000",
        normalized_value="5",
        reason="User-approved record-specific interpretation of 5000 metres as 5 km; "
        "original-source verification and separate approval, not an inferred unit rule",
    )
