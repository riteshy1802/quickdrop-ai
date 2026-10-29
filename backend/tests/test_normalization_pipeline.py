import csv
import shutil
from decimal import Decimal

import pytest

from app.data_quality.audit import analyze_distance_pattern
from app.data_quality.normalize import normalize_sources
from app.data_quality.rules import NormalizationError
from app.scripts.seed import DEFAULT_DATA_DIR


def test_reproducible_normalization_without_generic_conversion():
    first = normalize_sources(DEFAULT_DATA_DIR)
    second = normalize_sources(DEFAULT_DATA_DIR)
    assert first.rows == second.rows and first.report == second.report
    assert first.report["classification_counts"] == {
        "VALID": 6280,
        "CORRECTED": 65,
        "REQUIRES_REVIEW": 221,
        "INVALID": 0,
    }
    assert len(first.report["identical_duplicates_skipped"]) == 10
    corrections = first.report["corrections"]
    assert sum(c["field"] == "rider_id" for c in corrections) == 64
    assert sum(c["field"] == "distance_km" for c in corrections) == 1
    records = {r["trip_id"]: r for r in first.rows["trips"]}
    assert len(records) == 3304 and records["T312538"]["distance_km"] == 5
    for row in first.raw_rows["trips"]:
        if row["trip_id"] != "T312538":
            assert records[row["trip_id"]]["distance_km"] == row["distance_km"]
    assert first.rows["payout_lines"] == first.raw_rows["payout_lines"]
    assert sum(r["amount"] < 0 for r in first.rows["payout_lines"]) == 150
    assert all(
        item["effective_distance"] is None for item in first.report["records_requiring_review"]
    )
    evidence = analyze_distance_pattern(first)
    assert evidence["integer_values"] == evidence["multiples_of_100"] == 222
    assert evidence["completed_trip_historical_comparisons"] == {
        "matches_hypothetical_policy_fare": 202,
        "matches_hypothetical_unsurged_fare": 2,
    }


@pytest.mark.parametrize("case", ["unknown_rider", "conflicting_trip", "missing_canonical"])
def test_invalid_sources_block_automatic_normalization(tmp_path, case):
    for name in ["riders.csv", "trips.csv", "payout_lines.csv"]:
        shutil.copyfile(DEFAULT_DATA_DIR / name, tmp_path / name)
    path = tmp_path / ("riders.csv" if case == "missing_canonical" else "trips.csv")
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        rows = list(reader)
    if case == "unknown_rider":
        rows[0]["rider_id"] = "R999"
    elif case == "conflicting_trip":
        rows.append({**rows[0], "distance_km": "999"})
    else:
        rows = [r for r in rows if r["rider_id"] != "R007"]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(NormalizationError):
        normalize_sources(tmp_path)


def test_candidate_hypotheses_never_become_effective_values():
    bundle = normalize_sources(DEFAULT_DATA_DIR)
    quality = {q["source_id"]: q for q in bundle.report["records_requiring_review"]}
    assert "T312538" not in quality
    assert all(q["classification"] == "REQUIRES_REVIEW" for q in quality.values())
    assert all(q["issues"][0]["effective_value"] is None for q in quality.values())
    assert all(Decimal(q["original_distance"]) > 100 for q in quality.values())


def test_unrelated_valid_claims_and_incentives_do_not_inherit_distance_review():
    from datetime import UTC, date, datetime

    from app.services.financial.reconciliation import reconcile_records
    from app.services.financial.types import (
        ClaimRequest,
        FinancialSnapshot,
        PaymentEvidence,
        TripRecord,
    )

    records = tuple(
        TripRecord(
            trip_id=f"Q{i}",
            rider_id="R001",
            started_at=datetime(2026, 9, 20, 8, tzinfo=UTC),
            status="completed",
            distance_km=Decimal("3" if i == 0 else "2000"),
            surge_multiplier=Decimal("1"),
        )
        for i in range(12)
    )
    snapshot = FinancialSnapshot(rider_exists=True, source_data_complete=True, trips=records)
    received = datetime(2026, 9, 22, 8, tzinfo=UTC)
    proof = PaymentEvidence(rider_id="R001", provider_history_complete=True)
    valid = reconcile_records(
        ClaimRequest(rider_id="R001", received_at=received, trip_ids=("Q0",)), snapshot, proof
    )
    assert valid.status == "VERIFIED" and valid.outstanding == 31
    ambiguous = reconcile_records(
        ClaimRequest(rider_id="R001", received_at=received, trip_ids=("Q1",)), snapshot, proof
    )
    assert ambiguous.status == "REQUIRES_REVIEW" and ambiguous.outstanding is None
    assert ambiguous.items[0].data_quality_issues[0].effective_value is None
    incentive = reconcile_records(
        ClaimRequest(rider_id="R001", received_at=received, incentive_dates=(date(2026, 9, 20),)),
        snapshot,
        proof,
    )
    assert incentive.eligible and incentive.verified_shortfall == 150
