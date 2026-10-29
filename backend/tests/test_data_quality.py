import csv
import hashlib
import json
import shutil
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.scripts.audit_data import audit_data
from app.scripts.seed import DEFAULT_DATA_DIR
from app.services.financial.normalization import RULE_ID, normalize_trip_record
from app.services.financial.reconciliation import reconcile_records
from app.services.financial.types import (
    ClaimRequest,
    FinancialSnapshot,
    PaymentEvidence,
    PayoutRecord,
    TripRecord,
)


def original_trip():
    return TripRecord(
        trip_id="T312538",
        rider_id="R031",
        started_at=datetime(2026, 9, 18, 4, 47, tzinfo=UTC),
        status="completed",
        distance_km=Decimal("5000"),
        surge_multiplier=Decimal("1.5"),
    )


def test_exact_approved_normalization_is_pure_idempotent_and_derived():
    raw = original_trip()
    normalized, change = normalize_trip_record(raw)
    assert raw.distance_km == 5000 and normalized.distance_km == 5
    assert normalized.model_dump(exclude={"distance_km"}) == raw.model_dump(exclude={"distance_km"})
    assert change.rule_id == RULE_ID
    assert normalize_trip_record(normalized) == (normalized, None)
    request = ClaimRequest(
        rider_id="R031", received_at=datetime(2026, 9, 23, 5, tzinfo=UTC), trip_ids=("T312538",)
    )
    line = PayoutRecord(
        line_id="PL002492",
        rider_id="R031",
        trip_id="T312538",
        payout_date=raw.started_at.date(),
        line_type="trip",
        amount=Decimal("43"),
    )
    result = reconcile_records(
        request,
        FinancialSnapshot(
            rider_exists=True, source_data_complete=True, trips=(raw,), payouts=(line,)
        ),
        PaymentEvidence(rider_id="R031", provider_history_complete=True),
    )
    assert result.expected_amount == 65 and result.historical_paid == 43
    assert result.outstanding == 22 and result.verified_shortfall == 22
    assert result.data_quality_transformations == (change,)
    assert not result.payment_authorized


@pytest.mark.parametrize(
    "change",
    [
        {"trip_id": "T-other"},
        {"rider_id": "R032"},
        {"status": "cancelled_by_rider"},
        {"distance_km": Decimal("5001")},
        {"distance_km": Decimal("500")},
        {"surge_multiplier": Decimal("1.2")},
        {"started_at": datetime(2026, 9, 18, 4, 48, tzinfo=UTC)},
    ],
)
def test_no_other_record_or_revision_is_normalized(change):
    raw = original_trip().model_copy(update=change)
    assert normalize_trip_record(raw) == (raw, None)


def test_raw_csv_audit_is_reproducible_preserves_inputs_and_matches_report():
    paths = [DEFAULT_DATA_DIR / name for name in ["riders.csv", "trips.csv", "payout_lines.csv"]]
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    report = audit_data()
    assert audit_data() == report
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert {name: info["rows"] for name, info in report["sources"].items()} == {
        "riders.csv": 40,
        "trips.csv": 3314,
        "payout_lines.csv": 3222,
    }
    codes = report["summary"]["findings_by_code"]
    assert codes["UNUSUAL_DISTANCE"] == 222
    assert codes["IDENTICAL_DUPLICATE_ID"] == 10
    assert codes["APPROVED_RIDER_ALIAS"] == 64
    assert codes["MULTIPLE_PAYOUT_LINES_SAME_SOURCE"] == 4
    assert report["summary"]["metrics"] == {
        "negative_payout_lines": 150,
        "valid_negative_penalties": 150,
    }
    assert report["summary"]["findings_by_severity"].get("error", 0) == 0
    assert len(report["approved_transformations"]) == 1
    assert report["approved_transformations"][0]["source_id"] == "T312538"
    assert report["approved_transformations"][0]["row"] == 1979
    assert all(info["sha256"] == before[name] for name, info in report["sources"].items())
    committed = DEFAULT_DATA_DIR.parent / "backend/docs/data-quality-report.json"
    assert json.loads(committed.read_text()) == report


def rewrite(path, mutate):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        rows = list(reader)
    mutate(rows)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_audit_detects_invalid_fields_and_references_without_corrections(tmp_path):
    for name in ["riders.csv", "trips.csv", "payout_lines.csv"]:
        shutil.copyfile(DEFAULT_DATA_DIR / name, tmp_path / name)

    def dirty_trips(rows):
        rows[0].update(status="invalid", distance_km="-1", surge_multiplier="NaN", rider_id="R999")
        rows[1]["started_at"] = "2026-09-12T10:00:00"
        rows.append({**rows[2], "distance_km": "123"})

    def dirty_payouts(rows):
        rows[0]["amount"] = "-36"
        rows[1]["amount"] = "1.5"
        rows[2]["trip_id"] = "UNKNOWN"
        rows[5]["amount"] = "10"
        rows[6]["payout_date"] = "not-a-date"

    rewrite(tmp_path / "trips.csv", dirty_trips)
    rewrite(tmp_path / "payout_lines.csv", dirty_payouts)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    report = audit_data(tmp_path)
    codes = report["summary"]["findings_by_code"]
    for code in [
        "INVALID_TRIP_STATUS",
        "NEGATIVE_DISTANCE",
        "INVALID_NUMBER",
        "UNKNOWN_RIDER_REFERENCE",
        "INVALID_OR_NAIVE_TIMESTAMP",
        "CONFLICTING_DUPLICATE_ID",
        "NEGATIVE_NON_PENALTY_AMOUNT",
        "FRACTIONAL_PAYOUT_AMOUNT",
        "UNKNOWN_TRIP_REFERENCE",
        "NONNEGATIVE_PENALTY_AMOUNT",
        "INVALID_DATE",
    ]:
        assert codes[code] > 0, code
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_changed_known_record_is_reported_as_uncorrected(tmp_path):
    for name in ["riders.csv", "trips.csv", "payout_lines.csv"]:
        shutil.copyfile(DEFAULT_DATA_DIR / name, tmp_path / name)

    def change_source(rows):
        next(row for row in rows if row["trip_id"] == "T312538")["surge_multiplier"] = "1.2"

    rewrite(tmp_path / "trips.csv", change_source)
    report = audit_data(tmp_path)
    assert report["approved_transformations"] == []
    issue = next(
        f
        for f in report["findings"]
        if f["code"] == "UNUSUAL_DISTANCE" and f["source_id"] == "T312538"
    )
    assert issue["action"].startswith("Uncorrected")
