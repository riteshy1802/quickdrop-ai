"""Payment state and concurrency checks in the disposable PostgreSQL database."""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import get_session_factory
from app.integrations.payswift import PaySwiftClient, get_payswift_client
from app.main import create_app
from app.models import (
    AgentTrace,
    Conversation,
    Dispute,
    DisputeItem,
    OpsQueue,
    OpsUser,
    PaymentIntent,
    PayoutLine,
    Rider,
    Trip,
)
from app.repositories.payment_jobs import PaymentBusy, claim_job
from app.repositories.trips import IST
from app.services.auth_service import require_operator
from app.services.financial.types import ClaimRequest
from app.services.payment_authorization import authorize_payment
from app.services.payment_reconciliation import reference_for
from app.services.payment_worker import execute_job, process_one, reconcile_intent

pytestmark = pytest.mark.database


class MockProvider:
    def __init__(self):
        self.ledger = {}
        self.behavior = []
        self.posts = []
        self.gets = 0
        self.entered = None
        self.release = None
        self.bad_ledger = False

    async def handle(self, request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.method == "GET":
            self.gets += 1
            if self.bad_ledger:
                return httpx.Response(503, json={"error": "unavailable"})
            rows = [
                p for p in self.ledger.values() if p["rider_id"] == request.url.params["rider_id"]
            ]
            return httpx.Response(200, json={"data": rows, "count": len(rows)})
        body = json.loads(request.content)
        key = request.headers["Idempotency-Key"]
        self.posts.append((key, body))
        if self.entered is not None:
            self.entered.set()
            await self.release.wait()
        behavior = self.behavior.pop(0) if self.behavior else 201
        if behavior in (400, 409, 429, 500):
            return httpx.Response(
                behavior, json={"error": "controlled"}, headers={"Retry-After": "10"}
            )
        entry = self.ledger.setdefault(
            key,
            {
                **body,
                "payout_id": "pout_" + uuid4().hex[:12],
                "status": "processed",
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        if behavior == "lost":
            raise httpx.ReadTimeout("lost response after execution", request=request)
        if behavior == "lost-500":
            return httpx.Response(500, json={"error": "ambiguous"})
        return httpx.Response(201, json=entry)


@pytest_asyncio.fixture
async def provider():
    mock = MockProvider()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(mock.handle), base_url="http://provider"
    ) as http:
        yield PaySwiftClient(http), mock


@pytest_asyncio.fixture
async def payments(database_url):
    engine = create_async_engine(database_url, poolclass=NullPool, hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    rider = "P" + uuid4().hex[:20]
    operator_email = uuid4().hex + "@test.invalid"
    async with factory() as session, session.begin():
        session.add(
            Rider(rider_id=rider, name="Payment test", city="Test", joined_on=date(2026, 1, 1))
        )
        operator = OpsUser(
            email=operator_email, password_hash="test-only-not-used-for-authentication"
        )
        session.add(operator)
        await session.flush()
        operator_id = operator.id
    try:
        yield factory, rider, operator_id
    finally:
        async with factory() as session, session.begin():
            conversations = select(Conversation.id).where(Conversation.rider_id == rider)
            disputes = select(Dispute.id).where(Dispute.rider_id == rider)
            for model, condition in (
                (OpsQueue, OpsQueue.dispute_id.in_(disputes)),
                (PaymentIntent, PaymentIntent.rider_id == rider),
                (DisputeItem, DisputeItem.dispute_id.in_(disputes)),
                (Dispute, Dispute.rider_id == rider),
                (AgentTrace, AgentTrace.conversation_id.in_(conversations)),
                (Conversation, Conversation.rider_id == rider),
                (PayoutLine, PayoutLine.rider_id == rider),
                (Trip, Trip.rider_id == rider),
                (Rider, Rider.rider_id == rider),
                (OpsUser, OpsUser.id == operator_id),
            ):
                await session.execute(delete(model).where(condition))
        await engine.dispose()


async def create_case(factory, rider, amount=25):
    amount = Decimal(amount)
    now = datetime.now(UTC)
    day = now.astimezone(IST).date() - timedelta(days=1)
    trip_id = "T" + uuid4().hex[:20]
    async with factory() as session, session.begin():
        conversation = Conversation(rider_id=rider)
        session.add(conversation)
        session.add(
            Trip(
                trip_id=trip_id,
                rider_id=rider,
                started_at=datetime.combine(day, datetime.min.time(), IST) + timedelta(hours=12),
                status="completed",
                distance_km=Decimal(2) + amount / Decimal(6),
                surge_multiplier=Decimal(1),
            )
        )
        await session.flush()
        session.add(
            PayoutLine(
                line_id="L" + uuid4().hex[:20],
                rider_id=rider,
                trip_id=trip_id,
                payout_date=day,
                line_type="trip",
                amount=Decimal(25),
            )
        )
        dispute = Dispute(
            conversation_id=conversation.id,
            rider_id=rider,
            status="VERIFIED",
            verified_amount=amount,
        )
        session.add(dispute)
        await session.flush()
        session.add(
            DisputeItem(
                dispute_id=dispute.id,
                source_type="trip",
                source_id=trip_id,
                expected_amount=Decimal(25) + amount,
                actual_amount=Decimal(25),
                difference=amount,
            )
        )
        identifier = dispute.id
    return identifier, ClaimRequest(rider_id=rider, received_at=now, trip_ids=(trip_id,))


async def authorize(payments, provider, amount=25):
    factory, rider, _ = payments
    client, _ = provider
    identifier, request = await create_case(factory, rider, amount)
    result = await authorize_payment(
        factory, client, identifier, request, source_data_complete=True
    )
    return result, identifier, request


async def view(factory, identifier):
    async with factory() as session:
        return await session.get(PaymentIntent, identifier)


async def due(factory, identifier, *, expire=False):
    async with factory() as session, session.begin():
        intent = await session.get(PaymentIntent, identifier)
        intent.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
        if expire:
            intent.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)


async def test_success_duplicate_authorization_and_audit(payments, provider):
    factory, rider, _ = payments
    client, mock = provider
    result, identifier, request = await authorize(payments, provider)
    assert result.status == "AUTHORIZED"
    again = await authorize_payment(factory, client, identifier, request, source_data_complete=True)
    assert again.status == "EXISTING" and again.intent_id == result.intent_id
    assert not mock.posts
    assert await process_one(factory, client)
    intent = await view(factory, result.intent_id)
    assert intent.status == "SUCCEEDED" and intent.provider_payout_id.startswith("pout_")
    assert len(mock.ledger) == 1 and len(mock.posts) == 1
    for _ in range(3):
        assert not await process_one(factory, client)
    assert await reconcile_intent(factory, client, intent.id) == "SUCCEEDED"
    intent = await view(factory, intent.id)
    assert intent.last_reconciled_at is not None
    async with factory() as session:
        traces = list(
            await session.scalars(
                select(AgentTrace).join(Conversation).where(Conversation.rider_id == rider)
            )
        )
        assert {t.name for t in traces} >= {
            "payment_authorization",
            "payswift_request_started",
            "payswift_request_result",
        }
        assert (await session.get(Dispute, identifier)).status == "RESOLVED"
        assert (
            len(
                list(
                    await session.scalars(
                        select(PaymentIntent).where(PaymentIntent.rider_id == rider)
                    )
                )
            )
            == 1
        )


@pytest.mark.parametrize(
    "amount,status", [(200, "AUTHORIZED"), (201, "APPROVAL_REQUIRED"), (425, "APPROVAL_REQUIRED")]
)
async def test_full_amount_threshold(payments, provider, amount, status):
    factory, rider, _ = payments
    result, identifier, _ = await authorize(payments, provider, amount)
    assert result.status == status
    async with factory() as session:
        if status == "APPROVAL_REQUIRED":
            queue = await session.get(OpsQueue, result.queue_id)
            assert queue.amount == amount and queue.status == "PENDING"
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(PaymentIntent)
                    .where(PaymentIntent.dispute_id == identifier)
                )
                == 0
            )
        else:
            assert (await session.get(PaymentIntent, result.intent_id)).amount == amount


async def test_second_auto_and_concurrent_authorizations_require_ops(payments, provider):
    factory, rider, _ = payments
    client, _ = provider
    first, request1 = await create_case(factory, rider)
    second, request2 = await create_case(factory, rider)
    results = await asyncio.gather(
        authorize_payment(factory, client, first, request1, source_data_complete=True),
        authorize_payment(factory, client, second, request2, source_data_complete=True),
    )
    assert sorted(r.status for r in results) == ["APPROVAL_REQUIRED", "AUTHORIZED"]
    authorized = next(r for r in results if r.intent_id)
    async with factory() as session, session.begin():
        (await session.get(PaymentIntent, authorized.intent_id)).status = "UNKNOWN"
    third, request3 = await create_case(factory, rider)
    result = await authorize_payment(factory, client, third, request3, source_data_complete=True)
    assert result.status == "APPROVAL_REQUIRED"
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PaymentIntent)
                .where(PaymentIntent.rider_id == rider)
            )
            == 1
        )


async def test_concurrent_duplicate_authorization_creates_one_intent(payments, provider):
    factory, rider, _ = payments
    client, _ = provider
    identifier, request = await create_case(factory, rider)
    results = await asyncio.gather(
        *[
            authorize_payment(factory, client, identifier, request, source_data_complete=True)
            for _ in range(2)
        ]
    )
    assert {r.status for r in results} == {"AUTHORIZED", "EXISTING"}
    assert len({r.intent_id for r in results}) == 1


async def test_approved_full_balance_uses_ops_intent(payments, provider):
    factory, rider, operator = payments
    client, mock = provider
    result, identifier, request = await authorize(payments, provider, 425)
    async with factory() as session, session.begin():
        queue = await session.get(OpsQueue, result.queue_id)
        queue.status = "APPROVED"
        queue.assigned_to = operator
        queue.resolved_at = datetime.now(UTC)
    result = await authorize_payment(
        factory, client, identifier, request, source_data_complete=True
    )
    assert result.status == "AUTHORIZED"
    intent = await view(factory, result.intent_id)
    assert (
        intent.amount == 425
        and intent.payment_type == "OPS_APPROVED"
        and intent.auto_pay_date is None
    )
    assert await process_one(factory, client)
    assert len(mock.ledger) == 1 and mock.posts[0][1]["amount"] == 425


@pytest.mark.parametrize("behavior,expected", [(400, "FAILED"), (409, "UNKNOWN"), (500, "UNKNOWN")])
async def test_rejected_and_ambiguous_posts(payments, provider, behavior, expected):
    factory, _, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    mock.behavior = [behavior]
    assert await process_one(factory, client)
    assert (await view(factory, result.intent_id)).status == expected
    if expected == "UNKNOWN":
        await due(factory, result.intent_id)
        assert await process_one(factory, client)
        assert (await view(factory, result.intent_id)).status == "UNKNOWN"
    assert len(mock.posts) == 1  # No blind replay after an empty ledger.


async def test_429_schedules_same_key_and_respects_retry_after(payments, provider):
    factory, _, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    mock.behavior = [429, 201]
    assert await process_one(factory, client)
    waiting = await view(factory, result.intent_id)
    assert waiting.status == "PENDING" and waiting.post_started_at is None
    assert waiting.next_retry_at > datetime.now(UTC) + timedelta(seconds=8)
    assert not await process_one(factory, client)
    await due(factory, result.intent_id)
    assert await process_one(factory, client)
    assert len(mock.ledger) == 1 and len(mock.posts) == 2
    assert mock.posts[0] == mock.posts[1]


@pytest.mark.parametrize("behavior", ["lost", "lost-500"])
async def test_lost_response_reconciles_without_second_post(payments, provider, behavior):
    factory, _, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    mock.behavior = [behavior]
    assert await process_one(factory, client)
    assert (await view(factory, result.intent_id)).status == "UNKNOWN"
    await due(factory, result.intent_id)
    assert await process_one(factory, client)
    assert (await view(factory, result.intent_id)).status == "SUCCEEDED"
    assert len(mock.posts) == 1 and len(mock.ledger) == 1


async def test_worker_crash_after_provider_execution_recovers_by_get(payments, provider):
    factory, _, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    job = await claim_job(factory, max_attempts=8)
    outcome = await client.post(
        rider_id=job.rider_id,
        amount=int(job.amount),
        reference=job.reference,
        idempotency_key=job.idempotency_key,
    )
    assert outcome.kind == "CONFIRMED"  # Simulate crash before DB completion.
    await due(factory, result.intent_id, expire=True)
    recovered = await claim_job(factory, max_attempts=8)
    assert recovered.operation == "RECONCILE" and recovered.token != job.token
    assert await execute_job(factory, client, recovered, max_attempts=8) == "SUCCEEDED"
    from app.services.payment_worker import finish

    assert await finish(factory, job, outcome, max_attempts=8) is None
    assert len(mock.posts) == 1


async def test_crash_before_network_and_provider_reset_never_repost(payments, provider):
    factory, _, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    job = await claim_job(factory, max_attempts=3)
    assert job.operation == "POST"
    await due(factory, result.intent_id, expire=True)
    for _ in range(3):
        await process_one(factory, client, max_attempts=3)
        await due(factory, result.intent_id)
    assert (await view(factory, result.intent_id)).status == "NEEDS_REVIEW"
    assert len(mock.posts) == 0


async def test_two_workers_cannot_claim_same_active_job(payments, provider):
    factory, _, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    mock.entered, mock.release = asyncio.Event(), asyncio.Event()
    first = asyncio.create_task(process_one(factory, client))
    await asyncio.wait_for(mock.entered.wait(), 2)
    assert not await process_one(factory, client)
    mock.release.set()
    assert await first
    assert (await view(factory, result.intent_id)).status == "SUCCEEDED" and len(mock.posts) == 1


async def test_ledger_restart_preserves_success_and_blocks_new_authorization(payments, provider):
    factory, rider, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    assert await process_one(factory, client)
    mock.ledger.clear()
    assert await reconcile_intent(factory, client, result.intent_id) == "SUCCEEDED"
    assert len(mock.posts) == 1
    identifier, request = await create_case(factory, rider)
    blocked = await authorize_payment(
        factory, client, identifier, request, source_data_complete=True
    )
    assert blocked.status == "BLOCKED" and "missing" in blocked.reason


async def test_unknown_ledger_reset_stays_unknown_and_never_posts_again(payments, provider):
    factory, _, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    mock.behavior = ["lost"]
    await process_one(factory, client)
    mock.ledger.clear()
    await due(factory, result.intent_id)
    await process_one(factory, client)
    assert (await view(factory, result.intent_id)).status == "UNKNOWN" and len(mock.posts) == 1


async def test_changed_evidence_and_expired_ist_day_block_dispatch(payments, provider):
    factory, _, _ = payments
    client, mock = provider
    result, identifier, _ = await authorize(payments, provider)
    async with factory() as session, session.begin():
        intent = await session.get(PaymentIntent, result.intent_id)
        intent.auto_pay_date -= timedelta(days=1)
    await process_one(factory, client)
    assert (await view(factory, result.intent_id)).status == "NEEDS_REVIEW" and not mock.posts
    async with factory() as session, session.begin():
        intent = await session.get(PaymentIntent, result.intent_id)
        intent.status = "PENDING"
        intent.auto_pay_date = datetime.now(UTC).astimezone(IST).date()
        item = await session.scalar(select(DisputeItem).where(DisputeItem.dispute_id == identifier))
        item.difference = Decimal(26)
    await process_one(factory, client)
    assert (await view(factory, result.intent_id)).status == "NEEDS_REVIEW" and not mock.posts


async def test_missing_source_coverage_or_ledger_blocks_authorization(payments, provider):
    factory, rider, _ = payments
    client, mock = provider
    identifier, request = await create_case(factory, rider)
    result = await authorize_payment(
        factory, client, identifier, request, source_data_complete=False
    )
    assert result.status == "BLOCKED"
    mock.bad_ledger = True
    result = await authorize_payment(
        factory, client, identifier, request, source_data_complete=True
    )
    assert result.status == "BLOCKED" and not mock.posts


async def test_reconcile_api_is_guarded_and_get_only(payments, provider, monkeypatch):
    from app.core import access
    from app.core.config import Settings

    monkeypatch.setattr(
        access, "get_settings", lambda: Settings(_env_file=None, enable_local_internal_reads=False)
    )
    factory, _, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_payswift_client] = lambda: client
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.post(f"/ui/ops/payouts/{result.intent_id}/reconcile")
        assert response.status_code == 401
        app.dependency_overrides[require_operator] = lambda: None
        response = await http.post(f"/ui/ops/payouts/{result.intent_id}/reconcile")
        assert response.status_code == 200 and response.json()["status"] == "PENDING"
        assert not mock.posts
        assert (await http.post(f"/ui/ops/payouts/{uuid4()}/reconcile")).status_code == 404
    job = await claim_job(factory, max_attempts=8, identifier=result.intent_id, manual=True)
    with pytest.raises(PaymentBusy):
        await reconcile_intent(factory, client, result.intent_id)
    assert job.operation == "RECONCILE"


async def test_new_historical_credit_blocks_dispatch_overpayment(payments, provider):
    factory, rider, _ = payments
    client, mock = provider
    result, _, request = await authorize(payments, provider)
    async with factory() as session, session.begin():
        trip = await session.get(Trip, request.trip_ids[0])
        session.add(
            PayoutLine(
                line_id="L" + uuid4().hex[:20],
                rider_id=rider,
                trip_id=trip.trip_id,
                payout_date=trip.started_at.astimezone(IST).date(),
                line_type="trip",
                amount=Decimal(25),
            )
        )
    assert await process_one(factory, client)
    assert (await view(factory, result.intent_id)).status == "NEEDS_REVIEW"
    assert not mock.posts


async def test_overlapping_dispute_cannot_create_second_obligation(payments, provider):
    factory, rider, _ = payments
    client, mock = provider
    first, dispute_id, request = await authorize(payments, provider)
    async with factory() as session, session.begin():
        original = await session.get(Dispute, dispute_id)
        other = Dispute(
            conversation_id=original.conversation_id,
            rider_id=rider,
            status="VERIFIED",
            verified_amount=Decimal(25),
        )
        session.add(other)
        await session.flush()
        session.add(
            DisputeItem(
                dispute_id=other.id,
                source_type="trip",
                source_id=request.trip_ids[0],
                expected_amount=Decimal(50),
                actual_amount=Decimal(25),
                difference=Decimal(25),
            )
        )
        other_id = other.id
    blocked = await authorize_payment(factory, client, other_id, request, source_data_complete=True)
    assert blocked.status == "BLOCKED" and first.intent_id is not None
    assert not mock.posts


async def test_forged_or_partial_ops_approval_does_not_authorize(payments, provider):
    factory, _, operator = payments
    client, mock = provider
    result, identifier, request = await authorize(payments, provider, 425)
    async with factory() as session, session.begin():
        queue = await session.get(OpsQueue, result.queue_id)
        queue.status, queue.assigned_to, queue.resolved_at = "APPROVED", operator, datetime.now(UTC)
        queue.amount = Decimal(200)
    rejected = await authorize_payment(
        factory, client, identifier, request, source_data_complete=True
    )
    assert rejected.status == "BLOCKED" and not mock.posts


async def test_no_authorization_snapshot_means_no_post(payments, provider):
    factory, _, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    async with factory() as session, session.begin():
        (await session.get(PaymentIntent, result.intent_id)).authorization = None
    await process_one(factory, client)
    assert (await view(factory, result.intent_id)).status == "NEEDS_REVIEW" and not mock.posts


async def test_rate_limit_retry_budget_is_finite(payments, provider):
    factory, _, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    mock.behavior = [429, 429, 429]
    for _ in range(3):
        await process_one(factory, client, max_attempts=3)
        await due(factory, result.intent_id)
    assert (await view(factory, result.intent_id)).status == "NEEDS_REVIEW"
    assert len(mock.posts) == 3 and len({key for key, _ in mock.posts}) == 1
    assert not await process_one(factory, client, max_attempts=3)


async def test_unavailable_preflight_defers_without_post_and_recovers(payments, provider):
    factory, _, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    mock.bad_ledger = True
    await process_one(factory, client)
    intent = await view(factory, result.intent_id)
    assert intent.status == "PENDING" and intent.post_started_at is None and not mock.posts
    mock.bad_ledger = False
    await due(factory, intent.id)
    await process_one(factory, client)
    assert (await view(factory, intent.id)).status == "SUCCEEDED" and len(mock.posts) == 1


async def test_conflicting_manual_reconciliation_stops_pending_dispatch(payments, provider):
    factory, rider, _ = payments
    client, mock = provider
    result, _, _ = await authorize(payments, provider)
    mock.ledger["foreign-key"] = {
        "rider_id": rider,
        "amount": 26,
        "reference": reference_for(result.intent_id),
        "payout_id": "pout_" + uuid4().hex[:12],
        "status": "processed",
        "created_at": datetime.now(UTC).isoformat(),
    }
    assert await reconcile_intent(factory, client, result.intent_id) == "NEEDS_REVIEW"
    assert not await process_one(factory, client)
    assert not mock.posts
