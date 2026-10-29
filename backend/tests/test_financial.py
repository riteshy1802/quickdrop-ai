from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.services.financial.calculator import (
    cancellation_pay,
    completed_trip_pay,
    exact_sum,
    expected_total,
    round_rupees,
)
from app.services.financial.eligibility import date_eligibility
from app.services.financial.incentive import completed_trip_count, expected_incentive
from app.services.financial.reconciliation import reconcile_records
from app.services.financial.types import (
    Allocation,
    ClaimRequest,
    ConfirmedPayment,
    FinancialSnapshot,
    PaymentEvidence,
    PayoutRecord,
    PriorClaim,
    PriorIntent,
    PriorItem,
    TripRecord,
)

D = Decimal
DAY = date(2026, 9, 20)
RECEIVED = datetime.fromisoformat("2026-09-22T09:00:00+05:30")
FRESH = PaymentEvidence(rider_id="R1", provider_history_complete=True)


def trip(key="T1", *, rider="R1", status="completed", distance="2", surge="1", at=None):
    return TripRecord(
        trip_id=key,
        rider_id=rider,
        started_at=at or datetime(2026, 9, 20, 8, tzinfo=UTC),
        status=status,
        distance_km=D(distance),
        surge_multiplier=D(surge),
    )


def payout(key="P1", *, trip_id="T1", kind="trip", amount="0", day=DAY, rider="R1"):
    return PayoutRecord(
        line_id=key,
        rider_id=rider,
        trip_id=trip_id,
        payout_date=day,
        line_type=kind,
        amount=D(amount),
    )


def investigate(
    records=None,
    lines=(),
    *,
    scope=None,
    evidence=FRESH,
    claims=(),
    complete=True,
    rider_exists=True,
    received=RECEIVED,
):
    request = ClaimRequest(rider_id="R1", received_at=received, **(scope or {"trip_ids": ("T1",)}))
    snapshot = FinancialSnapshot(
        rider_exists=rider_exists,
        source_data_complete=complete,
        trips=tuple(records if records is not None else [trip()]),
        payouts=tuple(lines),
        prior_claims=tuple(claims),
    )
    return reconcile_records(request, snapshot, evidence)


@pytest.mark.parametrize(
    "distance,surge,expected",
    [
        ("0", "1", "25"),
        ("1.9", "1", "25"),
        ("2", "1", "25"),
        ("3", "1", "31"),
        ("2.1", "1", "26"),
        ("6.1", "1.5", "74"),
        ("2.25", "1", "27"),
        ("2", "1.1", "28"),
    ],
)
def test_completed_pay(distance, surge, expected):
    assert completed_trip_pay(D(distance), D(surge)) == D(expected)


def test_per_trip_rounding_and_ambient_context_independence():
    records = [trip("T1", distance="2.25"), trip("T2", distance="2.25")]
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        assert expected_total(records) == D("54")
        assert round_rupees(D("26.5")) == 27
        assert completed_trip_pay(D("6.1"), D("1.5")) == 74
        assert exact_sum([D("123456789.1234"), D("0.0001")]) == D("123456789.1235")
    assert expected_total(records + [records[0]]) == 54
    with pytest.raises(ValueError, match="Conflicting"):
        expected_total([trip(), trip(distance="3")])


@pytest.mark.parametrize("value", [1.5, D("NaN"), D("Infinity"), D("-1")])
def test_invalid_distance_rejected(value):
    with pytest.raises(ValueError):
        completed_trip_pay(value, D("1"))


@pytest.mark.parametrize("surge", [D("0"), D("-1"), D("NaN"), 1.5])
def test_invalid_surge_rejected(surge):
    with pytest.raises(ValueError):
        completed_trip_pay(D("2"), surge)


@pytest.mark.parametrize("count,expected", [(0, 0), (11, 0), (12, 150), (13, 150)])
def test_incentive_threshold(count, expected):
    assert expected_incentive(count) == expected


def test_incentive_excludes_cancellations_duplicates_and_other_riders_at_ist_midnight():
    start = datetime(2026, 9, 19, 18, 30, tzinfo=UTC)
    records = [trip(str(i), at=start + timedelta(minutes=i)) for i in range(12)]
    records += [
        records[0],
        trip("before", at=start - timedelta(microseconds=1)),
        trip("after", at=start + timedelta(days=1)),
        trip("other", rider="R2", at=start),
        trip("rider_cancel", status="cancelled_by_rider", at=start),
        trip("customer_cancel", status="cancelled_by_customer", at=start),
    ]
    assert completed_trip_count(records, "R1", DAY) == 12
    assert expected_incentive(completed_trip_count(records, "R1", DAY)) == 150


@pytest.mark.parametrize(
    "status,expected", [("cancelled_by_rider", -10), ("cancelled_by_customer", 0)]
)
def test_cancellation_policy(status, expected):
    assert cancellation_pay(status) == expected
    assert expected_total([trip(status=status)]) == expected


@pytest.mark.parametrize(
    "age,eligible", [(0, False), (-1, False), (1, True), (6, True), (7, True), (8, False)]
)
def test_seven_completed_ist_dates(age, eligible):
    assert date_eligibility(RECEIVED.date() - timedelta(days=age), RECEIVED).eligible is eligible


def test_window_uses_received_at_ist_not_utc_or_wall_clock():
    midnight = datetime(2026, 9, 21, 18, 30, tzinfo=UTC)  # 22 September IST.
    assert date_eligibility(date(2026, 9, 15), midnight).eligible
    assert not date_eligibility(date(2026, 9, 14), midnight).eligible
    assert date_eligibility(date(2026, 9, 14), midnight - timedelta(microseconds=1)).eligible
    with pytest.raises(ValueError, match="timezone"):
        date_eligibility(DAY, datetime(2026, 9, 22))


@pytest.mark.parametrize(
    "distance,surge,paid,expected,shortfall",
    [
        ("2", "1", "0", "25", "25"),  # Missing payment.
        ("2", "1", "10", "25", "15"),  # Partial payment.
        ("6.1", "1.5", "49", "74", "25"),  # Missing surge.
        ("7.4", "1", "25", "57", "32"),  # Missing distance compensation.
        ("2", "1", "25", "25", "0"),  # Exact pay.
        ("2", "1", "40", "25", "0"),  # Overpayment does not generate negative transfer.
    ],
)
def test_individual_trip_reconciliation(distance, surge, paid, expected, shortfall):
    lines = () if paid == "0" else [payout(amount=paid)]
    result = investigate([trip(distance=distance, surge=surge)], lines)
    assert result.expected_amount == D(expected)
    assert result.historical_paid == D(paid)
    assert result.raw_difference == D(expected) - D(paid)
    assert result.verified_shortfall == D(shortfall)
    assert result.outstanding == D(shortfall)
    assert not result.payment_authorized


def test_unrelated_overpayment_never_offsets_missing_trip():
    result = investigate(
        [trip("T1"), trip("T2")],
        [payout(trip_id="T2", amount="100")],
        scope={"trip_ids": ("T1", "T2", "T1")},
    )
    assert len(result.items) == 2
    assert result.raw_difference == -50
    assert result.verified_shortfall == 25 and result.outstanding == 25


def test_duplicate_penalties_preserve_distinct_line_ids():
    records = [trip(status="cancelled_by_rider")]
    first = payout("P1", kind="cancellation_penalty", amount="-10")
    second = payout("P2", kind="cancellation_penalty", amount="-10")
    result = investigate(records, [first, second, first])
    penalty = next(i for i in result.items if i.source_type == "penalty")
    assert penalty.expected_amount == -10 and penalty.historical_paid == -20
    assert penalty.historical_line_ids == ("P1", "P2")
    assert result.verified_shortfall == 10


def test_customer_cancellation_with_wrong_penalty_is_corrected():
    result = investigate(
        [trip(status="cancelled_by_customer")], [payout(kind="cancellation_penalty", amount="-10")]
    )
    assert result.verified_shortfall == 10
    assert all(i.expected_amount == 0 for i in result.items)


@pytest.mark.parametrize("paid,shortfall", [("0", 150), ("150", 0), ("300", 0)])
def test_daily_incentive_is_one_logical_source(paid, shortfall):
    records = [trip(f"T{i}") for i in range(13)]
    lines = () if paid == "0" else [payout(trip_id=None, kind="daily_incentive", amount=paid)]
    result = investigate(records, lines, scope={"incentive_dates": (DAY, DAY)})
    assert len(result.items) == 1
    assert result.items[0].source_id == DAY.isoformat()
    assert result.expected_amount == 150 and result.verified_shortfall == shortfall


@pytest.mark.parametrize(
    "case",
    [
        "wrong_owner",
        "missing_trip",
        "missing_rider",
        "partial_source",
        "wrong_date",
        "wrong_sign",
        "old",
        "no_daily_records",
        "conflicting_trip",
        "conflicting_line",
    ],
)
def test_unsafe_or_ineligible_sources_never_generate_money(case):
    kwargs = {}
    if case == "wrong_owner":
        kwargs["records"] = [trip(rider="R2")]
    if case == "missing_trip":
        kwargs["records"] = []
    if case == "missing_rider":
        kwargs["rider_exists"] = False
    if case == "partial_source":
        kwargs["complete"] = False
    if case == "wrong_date":
        kwargs["lines"] = [payout(amount="10", day=DAY + timedelta(days=1))]
    if case == "wrong_sign":
        kwargs["lines"] = [payout(amount="-10")]
    if case == "old":
        kwargs["received"] = RECEIVED + timedelta(days=10)
    if case == "no_daily_records":
        kwargs.update(records=[], scope={"incentive_dates": (DAY,)})
    if case == "conflicting_trip":
        kwargs["records"] = [trip(), trip(distance="10")]
    if case == "conflicting_line":
        kwargs["lines"] = [payout(amount="10"), payout(amount="20")]
    result = investigate(**kwargs)
    assert not result.eligible
    assert result.verified_shortfall == 0 and result.outstanding is None
    assert not result.payment_authorized


def test_missing_provider_evidence_preserves_shortfall_but_not_verified_outstanding():
    result = investigate(evidence=None)
    assert result.verified_shortfall == 25
    assert result.outstanding is None and result.requires_payment_reconciliation
    assert result.status == "NEEDS_RECONCILIATION"


def confirmation(amount="10", *, provider="pay-1", intent=None, trip_id="T1"):
    return ConfirmedPayment(
        provider_payout_id=provider,
        intent_id=intent,
        amount=D(amount),
        allocations=(
            Allocation(source_type="trip", source_id=trip_id, service_date=DAY, amount=D(amount)),
        ),
    )


def test_confirmed_adjustments_are_source_scoped_and_not_double_counted():
    known = confirmation()
    evidence = PaymentEvidence(
        rider_id="R1",
        provider_history_complete=True,
        confirmed=(known, known, confirmation("100", provider="unrelated", trip_id="T2")),
    )
    result = investigate(evidence=evidence)
    assert result.verified_shortfall == 25
    assert result.confirmed_adjustments == 10 and result.outstanding == 15
    assert result.model_dump(mode="json")["outstanding"] == "15"
    assert "payment_authorized" in result.model_dump(mode="json")


@pytest.mark.parametrize(
    "status",
    [
        "PENDING",
        "AWAITING_APPROVAL",
        "PROCESSING",
        "UNKNOWN",
        "NEEDS_REVIEW",
        "FAILED",
        "SUCCEEDED",
    ],
)
def test_existing_intents_require_provider_reconciliation(status):
    intent = PriorIntent(id=uuid4(), status=status, amount=D("25"), provider_payout_id="pay-1")
    claim = PriorClaim(
        id=uuid4(),
        status="PAYMENT_PENDING",
        items=(PriorItem(source_type="trip", source_id="T1"),),
        intents=(intent,),
    )
    result = investigate(claims=[claim])
    assert result.verified_shortfall == 25 and result.outstanding is None
    assert intent.id in result.items[0].blocking_intent_ids


def test_settled_dispute_and_unscoped_intents_block_duplicate_payment():
    claim = PriorClaim(
        id=uuid4(), status="RESOLVED", items=(PriorItem(source_type="trip", source_id="T1"),)
    )
    result = investigate(claims=[claim])
    assert result.outstanding is None and claim.id in result.items[0].blocking_claim_ids
    intent = PriorIntent(id=uuid4(), status="UNKNOWN", amount=D("25"))
    claim = PriorClaim(id=uuid4(), status="PAYMENT_PENDING", intents=(intent,))
    assert investigate(claims=[claim]).outstanding is None


def test_provider_confirmed_successful_intent_is_accounted_without_new_authorization():
    intent = PriorIntent(id=uuid4(), status="SUCCEEDED", amount=D("25"), provider_payout_id="pay-1")
    claim = PriorClaim(
        id=uuid4(),
        status="RESOLVED",
        items=(PriorItem(source_type="trip", source_id="T1"),),
        intents=(intent,),
    )
    evidence = PaymentEvidence(
        rider_id="R1",
        provider_history_complete=True,
        confirmed=(confirmation("25", intent=intent.id),),
    )
    result = investigate(claims=[claim], evidence=evidence)
    assert result.outstanding == 0 and result.verified_shortfall == 25
    assert not result.requires_payment_reconciliation and not result.payment_authorized
    unknown = intent.model_copy(update={"status": "UNKNOWN"})
    assert (
        investigate(
            claims=[claim.model_copy(update={"intents": (unknown,)})], evidence=evidence
        ).outstanding
        is None
    )


def test_conflicting_provider_evidence_never_produces_outstanding():
    evidence = PaymentEvidence(
        rider_id="R1",
        provider_history_complete=True,
        confirmed=(confirmation(), confirmation("15")),
    )
    assert investigate(evidence=evidence).outstanding is None
    with pytest.raises(ValidationError, match="entire confirmed payment"):
        confirmation().model_copy().model_validate(
            {**confirmation().model_dump(), "amount": D("20")}
        )
    with pytest.raises(ValidationError, match="never float"):
        payout(amount="0").model_validate({**payout().model_dump(), "amount": 0.1})


@pytest.mark.parametrize("distance", ["100.01", "800", "5000"])
def test_unverified_distance_outliers_require_review(distance):
    result = investigate([trip(distance=distance)])
    assert result.status == "REQUIRES_REVIEW"
    assert result.items[0].data_quality == "REQUIRES_REVIEW"
    assert result.items[0].data_quality_issues[0].code == "DISTANCE_UNIT_AMBIGUOUS"
    assert result.verified_shortfall == 0 and result.outstanding is None
    assert not result.payment_authorized


def test_payment_evidence_for_another_rider_is_not_applied():
    evidence = PaymentEvidence(
        rider_id="R2", provider_history_complete=True, confirmed=(confirmation("25"),)
    )
    result = investigate(evidence=evidence)
    assert result.confirmed_adjustments == 0 and result.outstanding is None
    with pytest.raises(ValidationError, match="trusted rider"):
        PaymentEvidence(provider_history_complete=True)
