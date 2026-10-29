"""Investigate unit-format evidence without making a conversion decision."""

from collections import Counter, defaultdict
from decimal import Decimal

from app.data_quality.normalize import NormalizationBundle
from app.data_quality.rules import DISTANCE_REVIEW_THRESHOLD_KM
from app.services.financial.calculator import completed_trip_pay, exact_sum


def analyze_distance_pattern(bundle: NormalizationBundle) -> dict:
    trips = {t["trip_id"]: t for t in bundle.raw_rows["trips"]}
    paid = defaultdict(list)
    for row in bundle.raw_rows["payout_lines"]:
        if row["line_type"] == "trip":
            paid[row["trip_id"]].append(row["amount"])
    evidence = []
    matches = Counter()
    ordinary = [
        t["distance_km"] for t in trips.values() if t["distance_km"] <= DISTANCE_REVIEW_THRESHOLD_KM
    ]
    anomalies = [t for t in trips.values() if t["distance_km"] > DISTANCE_REVIEW_THRESHOLD_KM]
    for trip in sorted(anomalies, key=lambda r: r["trip_id"]):
        raw = trip["distance_km"]
        candidate = raw / Decimal("1000")
        historical = exact_sum(paid[trip["trip_id"]])
        row = {
            "trip_id": trip["trip_id"],
            "rider_id": trip["rider_id"],
            "status": trip["status"],
            "raw_distance": str(raw),
            "hypothetical_km_if_metres": str(candidate),
            "surge_multiplier": str(trip["surge_multiplier"]),
            "historical_trip_paid": str(historical),
            "has_trip_payout": bool(paid[trip["trip_id"]]),
            "hypothesis_is_not_an_effective_value": True,
        }
        if trip["status"] == "completed":
            raw_fare = completed_trip_pay(raw, trip["surge_multiplier"])
            candidate_fare = completed_trip_pay(candidate, trip["surge_multiplier"])
            without_surge = completed_trip_pay(candidate, Decimal("1"))
            if not paid[trip["trip_id"]]:
                comparison = "missing_trip_payout"
            elif historical == candidate_fare:
                comparison = "matches_hypothetical_policy_fare"
            elif historical == without_surge:
                comparison = "matches_hypothetical_unsurged_fare"
            else:
                comparison = "other_difference"
            matches[comparison] += 1
            row.update(
                raw_policy_expected=str(raw_fare),
                hypothetical_policy_expected=str(candidate_fare),
                comparison=comparison,
            )
        evidence.append(row)
    return {
        "unique_anomalous_trips": len(anomalies),
        "by_rider": dict(sorted(Counter(t["rider_id"] for t in anomalies).items())),
        "by_status": dict(sorted(Counter(t["status"] for t in anomalies).items())),
        "integer_values": sum(
            t["distance_km"] == t["distance_km"].to_integral_value() for t in anomalies
        ),
        "multiples_of_100": sum(t["distance_km"] % Decimal("100") == 0 for t in anomalies),
        "ordinary_distance_range_km": [str(min(ordinary)), str(max(ordinary))] if ordinary else [],
        "hypothetical_range_if_metres": [
            str(min(t["distance_km"] / Decimal("1000") for t in anomalies)),
            str(max(t["distance_km"] / Decimal("1000") for t in anomalies)),
        ]
        if anomalies
        else [],
        "completed_trip_historical_comparisons": dict(sorted(matches.items())),
        "conclusion": "A rider-clustered factor-of-1000 format problem is plausible "
        "and supported by "
        "numeric and historical-payment patterns. Neither underpayments nor reference "
        "outcomes independently prove physical distances. "
        "No general conversion is approved.",
        "automatic_applicability": (
            "Only T312538 with its approved complete fingerprint; no other distance changes"
        ),
        "records": evidence,
    }
