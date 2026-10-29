"""Normalization pipeline. Financial formulas are deliberately absent."""

import hashlib
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.data_quality.report import DataQualityIssue, DataQualityTransformation, TripQuality
from app.data_quality.rules import (
    DISTANCE_REVIEW_THRESHOLD_KM,
    NormalizationError,
    canonical_rider_reference,
    trip_correction,
)

if TYPE_CHECKING:
    from app.services.financial.types import TripRecord


@dataclass(frozen=True)
class NormalizationBundle:
    rows: dict[str, list[dict]]
    raw_rows: dict[str, list[dict]]
    report: dict


def prepare_trip(trip: "TripRecord") -> tuple["TripRecord", TripQuality]:
    values = trip.model_dump()
    correction = trip_correction(values, include_canonical=True)
    transformations = ()
    if correction:
        transformations = (DataQualityTransformation(**correction),)
        trip = trip.model_copy(update={"distance_km": Decimal("5")})
    day = trip.started_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
    if trip.distance_km > DISTANCE_REVIEW_THRESHOLD_KM:
        quality = TripQuality(
            source_id=trip.trip_id,
            classification="REQUIRES_REVIEW",
            service_date=day,
            original_distance=str(values["distance_km"]),
            effective_distance=None,
            issues=(
                DataQualityIssue(
                    code="DISTANCE_UNIT_AMBIGUOUS",
                    source_id=trip.trip_id,
                    classification="REQUIRES_REVIEW",
                    field="distance_km",
                    observed_value=str(trip.distance_km),
                    effective_value=None,
                    reason="Unverified distance units; no general conversion is approved",
                ),
            ),
        )
    else:
        quality = TripQuality(
            source_id=trip.trip_id,
            classification="CORRECTED" if correction else "VALID",
            service_date=day,
            original_distance="5000" if correction else str(trip.distance_km),
            effective_distance=str(trip.distance_km),
            transformations=transformations,
        )
    return trip, quality


def normalize_sources(data_dir: Path) -> NormalizationBundle:
    # Local imports preserve compatibility with the existing seed and audit entry points.
    from app.scripts.audit_data import audit_data
    from app.scripts.seed import read_datasets
    from app.services.financial.types import TripRecord

    audit = audit_data(data_dir)
    errors = [f for f in audit["findings"] if f["severity"] == "error"]
    if errors:
        raise NormalizationError(
            f"Source validation failed: {errors[0]['code']} "
            f"in {errors[0]['file']}; no automatic synchronization is allowed"
        )
    raw = read_datasets(data_dir)
    for filename, source in audit["sources"].items():
        if hashlib.sha256((data_dir / filename).read_bytes()).hexdigest() != source["sha256"]:
            raise NormalizationError("Source files changed during validation; rerun normalization")
    ids = {r["rider_id"] for r in raw["riders"]}
    rows = {key: [] for key in raw}
    corrections = []
    skipped = []
    review = []
    classes = Counter()
    for table, key in [("riders", "rider_id"), ("trips", "trip_id"), ("payout_lines", "line_id")]:
        seen = {}
        for number, original in enumerate(raw[table], 2):
            if original[key] in seen:
                if seen[original[key]] != original:
                    raise NormalizationError(f"{table}: conflicting duplicate {original[key]}")
                skipped.append(
                    {
                        "source_file": table + ".csv",
                        "source_id": original[key],
                        "skipped_row": number,
                        "rule_id": "IDENTICAL_SOURCE_ID_KEEP_FIRST_V1",
                    }
                )
                continue
            seen[original[key]] = original
            effective = dict(original)
            classification = "VALID"
            if table != "riders":
                canonical = canonical_rider_reference(original["rider_id"], ids)
                if canonical != original["rider_id"]:
                    effective["rider_id"] = canonical
                    classification = "CORRECTED"
                    corrections.append(
                        dict(
                            source_file=table + ".csv",
                            source_id=original[key],
                            row=number,
                            field="rider_id",
                            original_value=original["rider_id"],
                            normalized_value=canonical,
                            rule_id="APPROVED_RIDER_ALIASES_V1",
                            reason=(
                                "Previously approved exact alias; canonical ID exists in riders.csv"
                            ),
                        )
                    )
            if table == "trips":
                trip, quality = prepare_trip(TripRecord.model_validate(effective))
                if quality.classification == "CORRECTED":
                    effective["distance_km"] = trip.distance_km
                    classification = "CORRECTED"
                    corrections.extend(
                        {**c.model_dump(mode="json"), "row": number}
                        for c in quality.transformations
                    )
                elif quality.classification == "REQUIRES_REVIEW":
                    classification = "REQUIRES_REVIEW"
                    review.append(quality.model_dump(mode="json"))
                    # Preserve raw storage data.
                    # Effective distance remains explicitly unknown in the report.
            classes[classification] += 1
            rows[table].append(effective)
    for correction in corrections:
        correction["evidence"] = {
            "approval": (
                "Explicit prior user approval of the two exact rider aliases"
                if correction["field"] == "rider_id"
                else "Explicit prior user approval of the exact T312538 source correction"
            ),
            "source_sha256": audit["sources"][correction["source_file"]]["sha256"],
            "canonical_ids_validated_against": "riders.csv",
            "reference_outcome_alone_is_not_independent_proof": False,
        }
    report = {
        "report_version": 2,
        "original_sources": audit["sources"],
        "original_row_counts": {key: len(value) for key, value in raw.items()},
        "normalized_row_counts": {key: len(value) for key, value in rows.items()},
        "classification_counts": {
            key: classes[key] for key in ["VALID", "CORRECTED", "REQUIRES_REVIEW", "INVALID"]
        },
        "corrections": corrections,
        "identical_duplicates_skipped": skipped,
        "conflicting_duplicates": [],
        "invalid_rows": [],
        "records_requiring_review": review,
        "penalty_irregularities": [
            f for f in audit["findings"] if f["code"] == "MULTIPLE_PAYOUT_LINES_SAME_SOURCE"
        ],
        "raw_audit": audit,
        "storage_policy": (
            "Unresolved raw distances may be preserved in PostgreSQL; "
            "they are not effective distances"
        ),
    }
    return NormalizationBundle(rows=rows, raw_rows=raw, report=report)
