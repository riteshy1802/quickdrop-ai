"""Read-only, reproducible audit of original CSV exports. Never correct source files."""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.scripts.seed import APPROVED_RIDER_ALIASES, DEFAULT_DATA_DIR
from app.services.financial.normalization import normalize_trip_record
from app.services.financial.types import TripRecord

IST = ZoneInfo("Asia/Kolkata")
COLUMNS = {
    "riders.csv": ["rider_id", "name", "city", "joined_on"],
    "trips.csv": ["trip_id", "rider_id", "started_at", "status", "distance_km", "surge_multiplier"],
    "payout_lines.csv": ["line_id", "payout_date", "rider_id", "line_type", "trip_id", "amount"],
}
STATUSES = {"completed", "cancelled_by_rider", "cancelled_by_customer"}
LINE_TYPES = {"trip", "daily_incentive", "cancellation_penalty"}


def audit_data(data_dir: Path = DEFAULT_DATA_DIR) -> dict:
    findings = []
    sources = {}
    data = {}
    transformations = []
    metrics = Counter()

    def finding(code, filename, *, severity="warning", row=None, source_id=None, **details):
        findings.append(
            dict(
                code=code, severity=severity, file=filename, row=row, source_id=source_id, **details
            )
        )

        return findings[-1]

    for filename, columns in COLUMNS.items():
        path = data_dir / filename
        raw = path.read_bytes()
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            if set(reader.fieldnames or ()) != set(columns) or len(reader.fieldnames or ()) != len(
                columns
            ):
                finding("INVALID_HEADERS", filename, severity="error", observed=reader.fieldnames)
        sources[filename] = {"sha256": hashlib.sha256(raw).hexdigest(), "rows": len(rows)}
        data[filename] = rows
        primary_key = columns[0]
        grouped = defaultdict(list)
        for number, row in enumerate(rows, 2):
            source_id = row.get(primary_key)
            if None in row or any(value is None for value in row.values()):
                finding(
                    "MALFORMED_CSV_ROW", filename, severity="error", row=number, source_id=source_id
                )
            for field in columns:
                value = row.get(field)
                if (value is None or value == "") and not (
                    filename == "payout_lines.csv" and field == "trip_id"
                ):
                    finding(
                        "MISSING_VALUE",
                        filename,
                        severity="error",
                        row=number,
                        source_id=source_id,
                        field=field,
                    )
                elif isinstance(value, str) and value != value.strip():
                    finding(
                        "SURROUNDING_WHITESPACE",
                        filename,
                        row=number,
                        source_id=source_id,
                        field=field,
                    )
            grouped[source_id].append((number, row))
        for key, group in grouped.items():
            if len(group) > 1:
                identical = all(record == group[0][1] for _, record in group)
                finding(
                    "IDENTICAL_DUPLICATE_ID" if identical else "CONFLICTING_DUPLICATE_ID",
                    filename,
                    severity="info" if identical else "error",
                    source_id=key,
                    rows=[n for n, _ in group],
                    extra_rows=len(group) - 1,
                    action="Report only; identical trip IDs are already skipped by seeding",
                )

    def number(value, filename, row, source_id, field):
        try:
            parsed = Decimal(value)
            if not parsed.is_finite():
                raise InvalidOperation
            return parsed
        except (InvalidOperation, TypeError, ValueError):
            finding(
                "INVALID_NUMBER",
                filename,
                severity="error",
                row=row,
                source_id=source_id,
                field=field,
                observed=value,
            )
            return None

    def calendar(value, filename, row, source_id, field):
        try:
            return date.fromisoformat(value)
        except (ValueError, TypeError):
            finding(
                "INVALID_DATE",
                filename,
                severity="error",
                row=row,
                source_id=source_id,
                field=field,
                observed=value,
            )
            return None

    riders = {r.get("rider_id"): r for r in data["riders.csv"]}
    joins = {}
    for n, record in enumerate(data["riders.csv"], 2):
        key = record.get("rider_id")
        if not re.fullmatch(r"R\d{3}", key or ""):
            finding("NONCANONICAL_RIDER_ID", "riders.csv", row=n, source_id=key)
        joins[key] = calendar(record.get("joined_on"), "riders.csv", n, key, "joined_on")

    def rider_reference(value, filename, n, source_id):
        if value in riders:
            return value
        target = APPROVED_RIDER_ALIASES.get(value)
        if target is not None and target in riders:
            finding(
                "APPROVED_RIDER_ALIAS",
                filename,
                severity="info",
                row=n,
                source_id=source_id,
                observed=value,
                canonical=target,
                action="Previously approved seed-only reference mapping",
            )
            return target
        finding(
            "UNKNOWN_RIDER_REFERENCE",
            filename,
            severity="error",
            row=n,
            source_id=source_id,
            observed=value,
            action="Uncorrected",
        )
        return value

    trips = {}
    for n, record in enumerate(data["trips.csv"], 2):
        key = record.get("trip_id")
        rider = rider_reference(record.get("rider_id"), "trips.csv", n, key)
        status = record.get("status")
        if status not in STATUSES:
            finding(
                "INVALID_TRIP_STATUS",
                "trips.csv",
                severity="error",
                row=n,
                source_id=key,
                observed=status,
            )
        distance = number(record.get("distance_km"), "trips.csv", n, key, "distance_km")
        surge = number(record.get("surge_multiplier"), "trips.csv", n, key, "surge_multiplier")
        distance_issue = None
        if distance is not None:
            if distance < 0:
                finding(
                    "NEGATIVE_DISTANCE",
                    "trips.csv",
                    severity="error",
                    row=n,
                    source_id=key,
                    observed=str(distance),
                )
            if distance > 100:
                distance_issue = finding(
                    "UNUSUAL_DISTANCE",
                    "trips.csv",
                    row=n,
                    source_id=key,
                    rider_id=rider,
                    status=status,
                    observed=str(distance),
                    action="Uncorrected; source-unit review required",
                )
        if surge is not None and surge <= 0:
            finding(
                "INVALID_SURGE",
                "trips.csv",
                severity="error",
                row=n,
                source_id=key,
                observed=str(surge),
            )
        elif surge is not None and surge > 3:
            finding("UNUSUAL_SURGE", "trips.csv", row=n, source_id=key, observed=str(surge))
        day = None
        try:
            timestamp = datetime.fromisoformat(record.get("started_at", ""))
            if timestamp.utcoffset() is None:
                raise ValueError
            day = timestamp.astimezone(IST).date()
            if joins.get(rider) and day < joins[rider]:
                finding("TRIP_BEFORE_RIDER_JOINED", "trips.csv", row=n, source_id=key)
        except (ValueError, TypeError):
            finding(
                "INVALID_OR_NAIVE_TIMESTAMP",
                "trips.csv",
                severity="error",
                row=n,
                source_id=key,
                observed=record.get("started_at"),
            )
        trips.setdefault(key, {"rider_id": rider, "day": day, "status": status})
        try:
            trip = TripRecord.model_validate({**record, "rider_id": rider})
            _, change = normalize_trip_record(trip)
            if change:
                if distance_issue is not None:
                    distance_issue["action"] = "Approved exact-record correction"
                transformations.append(
                    {
                        **change.model_dump(mode="json"),
                        "row": n,
                        "application": (
                            "Financial read boundary only; CSV and stored raw trip stay unchanged"
                        ),
                    }
                )
        except (ValidationError, TypeError):
            pass  # Individual malformed fields are reported above, without stopping other checks.

    groups = defaultdict(list)
    paid_trip_ids = set()
    for n, record in enumerate(data["payout_lines.csv"], 2):
        key = record.get("line_id")
        rider = rider_reference(record.get("rider_id"), "payout_lines.csv", n, key)
        kind = record.get("line_type")
        if kind not in LINE_TYPES:
            finding(
                "INVALID_LINE_TYPE",
                "payout_lines.csv",
                severity="error",
                row=n,
                source_id=key,
                observed=kind,
            )
        amount = number(record.get("amount"), "payout_lines.csv", n, key, "amount")
        if amount is not None:
            if amount < 0:
                metrics["negative_payout_lines"] += 1
                if kind == "cancellation_penalty":
                    metrics["valid_negative_penalties"] += 1
                else:
                    finding(
                        "NEGATIVE_NON_PENALTY_AMOUNT",
                        "payout_lines.csv",
                        severity="error",
                        row=n,
                        source_id=key,
                        observed=str(amount),
                    )
            if kind == "cancellation_penalty" and amount >= 0:
                finding(
                    "NONNEGATIVE_PENALTY_AMOUNT",
                    "payout_lines.csv",
                    row=n,
                    source_id=key,
                    observed=str(amount),
                )
            if amount == 0:
                finding(
                    "ZERO_PAYOUT_AMOUNT", "payout_lines.csv", severity="info", row=n, source_id=key
                )
            if amount != amount.to_integral_value():
                finding(
                    "FRACTIONAL_PAYOUT_AMOUNT",
                    "payout_lines.csv",
                    row=n,
                    source_id=key,
                    observed=str(amount),
                )
            if abs(amount) > 1000:
                finding(
                    "UNUSUAL_PAYOUT_AMOUNT",
                    "payout_lines.csv",
                    row=n,
                    source_id=key,
                    observed=str(amount),
                )
        day = calendar(record.get("payout_date"), "payout_lines.csv", n, key, "payout_date")
        trip_id = record.get("trip_id")
        if not trip_id and kind != "daily_incentive":
            finding(
                "MISSING_TRIP_REFERENCE", "payout_lines.csv", severity="error", row=n, source_id=key
            )
        if trip_id:
            trip = trips.get(trip_id)
            if trip is None:
                finding(
                    "UNKNOWN_TRIP_REFERENCE",
                    "payout_lines.csv",
                    severity="error",
                    row=n,
                    source_id=key,
                    trip_id=trip_id,
                )
            else:
                if trip["rider_id"] != rider:
                    finding(
                        "TRIP_RIDER_MISMATCH",
                        "payout_lines.csv",
                        severity="error",
                        row=n,
                        source_id=key,
                        trip_id=trip_id,
                    )
                if day and trip["day"] and day != trip["day"]:
                    finding(
                        "PAYOUT_TRIP_DATE_MISMATCH",
                        "payout_lines.csv",
                        row=n,
                        source_id=key,
                        trip_id=trip_id,
                    )
                if kind == "trip" and trip["status"] != "completed":
                    finding(
                        "TRIP_PAY_ON_CANCELLED_TRIP",
                        "payout_lines.csv",
                        row=n,
                        source_id=key,
                        trip_id=trip_id,
                    )
                if kind == "cancellation_penalty" and trip["status"] != "cancelled_by_rider":
                    finding(
                        "PENALTY_WITHOUT_RIDER_CANCELLATION",
                        "payout_lines.csv",
                        row=n,
                        source_id=key,
                        trip_id=trip_id,
                    )
            if kind == "trip":
                paid_trip_ids.add(trip_id)
        if kind == "daily_incentive" and trip_id:
            finding("INCENTIVE_HAS_TRIP_REFERENCE", "payout_lines.csv", row=n, source_id=key)
        groups[(rider, record.get("payout_date"), kind, trip_id)].append(record)
    for (rider, day, kind, trip_id), records in sorted(
        groups.items(), key=lambda item: str(item[0])
    ):
        if len(records) > 1:
            finding(
                "MULTIPLE_PAYOUT_LINES_SAME_SOURCE",
                "payout_lines.csv",
                source_id=trip_id,
                rider_id=rider,
                service_date=day,
                line_type=kind,
                line_ids=[r.get("line_id") for r in records],
                amounts=[r.get("amount") for r in records],
                action="Retained as separate historical records; never deduplicate deductions",
            )
    missing = [
        key
        for key, trip in trips.items()
        if trip["status"] == "completed" and key not in paid_trip_ids
    ]
    if missing:
        finding(
            "COMPLETED_TRIPS_WITHOUT_TRIP_PAYOUT",
            "payout_lines.csv",
            severity="info",
            trip_ids=sorted(missing),
            count=len(missing),
            action="Financial investigation required; absence is not an automatic data correction",
        )
    counts = Counter(f["code"] for f in findings)
    return {
        "report_version": 1,
        "sources": sources,
        "scope": "Raw CSV audit; no source or database mutations",
        "review_screens": {
            "distance_km_above": "100",
            "surge_above": "3",
            "absolute_payout_above": "1000",
            "meaning": "Review-only heuristics, not official payout policy limits",
        },
        "summary": {
            "findings_by_code": dict(sorted(counts.items())),
            "findings_by_severity": dict(sorted(Counter(f["severity"] for f in findings).items())),
            "metrics": dict(sorted(metrics.items())),
        },
        "approved_transformations": transformations,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit_data(args.data_dir)
        output = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
    except (OSError, UnicodeError, csv.Error) as exc:
        print(f"Audit failed: {type(exc).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
