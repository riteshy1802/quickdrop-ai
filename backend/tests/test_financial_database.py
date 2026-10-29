import json
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from app.core.config import BACKEND_DIR
from app.models import Conversation, Dispute, DisputeItem, PaymentIntent
from app.services.financial.reconciliation import reconcile
from app.services.financial.types import Allocation, ClaimRequest, ConfirmedPayment, PaymentEvidence

pytestmark = pytest.mark.database
REFERENCES = json.loads((BACKEND_DIR.parent / "data/conversations.json").read_text())


def reference(rider_id):
    return next(c for c in REFERENCES if c["rider_id"] == rider_id)


def request_for(rider_id, **scope):
    source = reference(rider_id)
    received = next(t["received_at"] for t in source["turns"] if t["from"] == "rider")
    return ClaimRequest(rider_id=rider_id, received_at=datetime.fromisoformat(received), **scope)


@pytest.mark.parametrize(
    "rider,scope",
    [
        ("R003", {"trip_ids": ("T926334",)}),
        ("R005", {"incentive_dates": (date(2026, 9, 21),)}),
        ("R014", {"penalty_dates": (date(2026, 9, 18),)}),
        ("R033", {"trip_ids": ("T795007", "T206956")}),
        ("R016", {"trip_dates": (date(2026, 9, 19),)}),
        ("R024", {"incentive_dates": (date(2026, 9, 18),)}),
        ("R025", {"incentive_dates": (date(2026, 9, 19),)}),
        ("R007", {"trip_ids": ("T840677",)}),
        ("R026", {"trip_ids": ("T672899",)}),
        ("R035", {"trip_ids": ("T980582",)}),
        ("R011", {"incentive_dates": (date(2026, 9, 19),)}),
        ("R009", {"incentive_dates": (date(2026, 9, 17),)}),
        ("R036", {"trip_ids": ("T990831",)}),
        ("R028", {"trip_ids": ("T849302",)}),
    ],
)
async def test_real_assignment_scenarios(session, seeded, rider, scope):
    result = await reconcile(session, request_for(rider, **scope), source_data_complete=True)
    expected = reference(rider)["expected"]
    shortfall = Decimal(expected.get("payout", 0)) + Decimal(expected.get("approval") or 0)
    assert result.eligible
    assert result.verified_shortfall == shortfall
    assert result.payment_authorized is False
    # Seeded historical exports alone never claim a provider-confirmed outstanding balance.
    if shortfall:
        assert result.outstanding is None and result.requires_payment_reconciliation
    if rider == "R003":
        assert result.items[0].expected_amount == 74 and result.items[0].historical_paid == 49
    if rider == "R016":
        assert sorted(i.verified_shortfall for i in result.items if i.verified_shortfall) == [
            73,
            85,
            85,
            91,
            91,
        ]
    if rider == "R014":
        assert len(result.items) == 1
        assert len(result.items[0].historical_line_ids) == 2


async def test_multiple_discrepancies_remain_separate(session, seeded):
    request = request_for(
        "R027", trip_dates=(date(2026, 9, 20),), penalty_dates=(date(2026, 9, 21),)
    )
    result = await reconcile(session, request, source_data_complete=True)
    assert sorted(i.verified_shortfall for i in result.items if i.verified_shortfall) == [10, 15]
    assert result.verified_shortfall == 25
    assert result.payment_authorized is False


async def test_historical_timestamp_and_ownership_rejections(session, seeded):
    old = await reconcile(
        session, request_for("R022", trip_ids=("T502951",)), source_data_complete=True
    )
    assert not old.eligible and old.verified_shortfall == 0
    assert "seven" in " ".join(old.items[0].reasons)
    wrong = await reconcile(
        session, request_for("R021", trip_ids=("T482410",)), source_data_complete=True
    )
    assert not wrong.eligible and wrong.verified_shortfall == 0
    missing = await reconcile(
        session, request_for("R003", trip_ids=("unknown-trip",)), source_data_complete=True
    )
    assert not missing.eligible and missing.verified_shortfall == 0
    assert missing.items[0].service_date is None


async def create_prior(session, *, status, scoped=True):
    conversation = Conversation(rider_id="R003")
    session.add(conversation)
    await session.flush()
    dispute = Dispute(
        rider_id="R003",
        conversation_id=conversation.id,
        status="RESOLVED" if status == "SUCCEEDED" else "PAYMENT_PENDING",
        verified_amount=Decimal("25"),
    )
    session.add(dispute)
    await session.flush()
    if scoped:
        session.add(
            DisputeItem(
                dispute_id=dispute.id,
                source_type="trip",
                source_id="T926334",
                expected_amount=Decimal("74"),
                actual_amount=Decimal("49"),
                difference=Decimal("25"),
            )
        )
    intent = PaymentIntent(
        dispute_id=dispute.id,
        rider_id="R003",
        amount=Decimal("25"),
        status=status,
        payment_type="AUTO",
        auto_pay_date=date(2026, 9, 22),
        idempotency_key=uuid4().hex,
        provider_payout_id="provider-1",
    )
    session.add(intent)
    await session.flush()
    return intent


@pytest.mark.parametrize("status", ["PENDING", "UNKNOWN", "SUCCEEDED", "FAILED"])
async def test_persisted_payment_state_blocks_another_adjustment(session, seeded, status):
    intent = await create_prior(session, status=status)
    result = await reconcile(
        session,
        request_for("R003", trip_ids=("T926334",)),
        source_data_complete=True,
        evidence=PaymentEvidence(rider_id="R003", provider_history_complete=True),
    )
    assert result.verified_shortfall == 25 and result.outstanding is None
    assert intent.id in result.items[0].blocking_intent_ids
    assert not result.payment_authorized


async def test_success_is_not_assumed_from_database_status(session, seeded):
    intent = await create_prior(session, status="SUCCEEDED")
    confirmed = ConfirmedPayment(
        provider_payout_id="provider-1",
        intent_id=intent.id,
        amount=Decimal("25"),
        allocations=(
            Allocation(
                source_type="trip",
                source_id="T926334",
                service_date=date(2026, 9, 20),
                amount=Decimal("25"),
            ),
        ),
    )
    result = await reconcile(
        session,
        request_for("R003", trip_ids=("T926334",)),
        source_data_complete=True,
        evidence=PaymentEvidence(
            rider_id="R003", provider_history_complete=True, confirmed=(confirmed,)
        ),
    )
    assert result.verified_shortfall == 25 and result.outstanding == 0
    assert not result.requires_payment_reconciliation and not result.payment_authorized


async def test_prior_intent_without_source_items_is_not_ignored(session, seeded):
    intent = await create_prior(session, status="UNKNOWN", scoped=False)
    result = await reconcile(
        session, request_for("R003", trip_ids=("T926334",)), source_data_complete=True
    )
    assert result.outstanding is None and intent.id in result.items[0].blocking_intent_ids


async def test_batched_read_only_repository_integration(session, connection, seeded):
    statements = []
    bind = connection.sync_connection

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    before = await session.scalar(select(func.count()).select_from(PaymentIntent))
    pending = Conversation(rider_id="R016")
    session.add(pending)
    event.listen(bind, "before_cursor_execute", record)
    try:
        result = await reconcile(
            session, request_for("R016", trip_dates=(date(2026, 9, 19),)), source_data_complete=True
        )
    finally:
        event.remove(bind, "before_cursor_execute", record)
    assert result.verified_shortfall == 425
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert len(statements) <= 6
    assert pending in session.new  # The read-only service did not autoflush caller writes.
    session.expunge(pending)
    assert await session.scalar(select(func.count()).select_from(PaymentIntent)) == before


async def test_approved_reference_distance_normalization(session, seeded):
    from app.models import Trip

    raw = await session.get(Trip, "T312538")
    assert raw.distance_km == Decimal("5000")
    request = request_for("R031", trip_ids=("T312538",))
    result = await reconcile(session, request, source_data_complete=True)
    assert result.eligible and result.expected_amount == 65
    assert result.historical_paid == 43
    assert result.verified_shortfall == reference("R031")["expected"]["payout"] == 22
    assert result.outstanding is None  # Provider history still needs independent reconciliation.
    assert len(result.data_quality_transformations) == 1
    change = result.data_quality_transformations[0]
    assert change.source_id == "T312538" and change.original_value == "5000"
    assert change.normalized_value == "5"
    confirmed_history = PaymentEvidence(rider_id="R031", provider_history_complete=True)
    settled = await reconcile(
        session, request, source_data_complete=True, evidence=confirmed_history
    )
    assert settled.outstanding == 22 and not settled.payment_authorized
    await session.refresh(raw)
    assert raw.distance_km == 5000  # Raw database provenance is preserved too.
