"""Endpoint and real concurrency checks. Only the disposable test DB is used."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.access import require_local_development
from app.core.database import get_db_session, get_session_factory
from app.main import create_app
from app.models import (
    AgentTrace,
    Conversation,
    Dispute,
    DisputeItem,
    Message,
    OpsQueue,
    PaymentIntent,
    Rider,
)
from app.services import message_service, trace_service
from app.services.auth_service import require_operator

pytestmark = pytest.mark.database


@pytest_asyncio.fixture
async def api(database_url, monkeypatch):
    async def legacy_handler(factory, claim):
        return await message_service.deterministic_handler(claim)

    monkeypatch.setattr(message_service, "run_handler", legacy_handler)
    # Separate real connections and commits are essential for webhook concurrency proof.
    engine = create_async_engine(database_url, poolclass=NullPool, hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    rider_id = "M" + uuid4().hex[:20]
    other_id = "N" + uuid4().hex[:20]
    async with factory() as session, session.begin():
        session.add_all(
            [
                Rider(
                    rider_id=identifier, name="Test rider", city="Test", joined_on=date(2026, 9, 1)
                )
                for identifier in (rider_id, other_id)
            ]
        )
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[require_local_development] = lambda: None
    app.dependency_overrides[require_operator] = lambda: None

    async def dependency():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = dependency
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, factory, rider_id, other_id
    finally:
        # Remove only this fixture's records, preserving any other test's committed data.
        async with factory() as session, session.begin():
            conversations = select(Conversation.id).where(
                Conversation.rider_id.in_((rider_id, other_id))
            )
            disputes = select(Dispute.id).where(Dispute.rider_id.in_((rider_id, other_id)))
            for model, condition in (
                (OpsQueue, OpsQueue.dispute_id.in_(disputes)),
                (PaymentIntent, PaymentIntent.rider_id.in_((rider_id, other_id))),
                (DisputeItem, DisputeItem.dispute_id.in_(disputes)),
                (Dispute, Dispute.rider_id.in_((rider_id, other_id))),
                (AgentTrace, AgentTrace.conversation_id.in_(conversations)),
                (Message, Message.conversation_id.in_(conversations)),
                (Conversation, Conversation.rider_id.in_((rider_id, other_id))),
                (Rider, Rider.rider_id.in_((rider_id, other_id))),
            ):
                await session.execute(delete(model).where(condition))
        await engine.dispose()


def payload(rider_id, **changes):
    return {
        "message_id": "wamid." + uuid4().hex,
        "rider_id": rider_id,
        "text": "R003 payout concern, trip T926334",
        "received_at": "2026-09-22T09:05:00+05:30",
        **changes,
    }


async def counts(factory, rider_id):
    async with factory() as session:
        conversation_ids = select(Conversation.id).where(Conversation.rider_id == rider_id)
        return tuple(
            [
                await session.scalar(select(func.count()).select_from(model).where(condition))
                for model, condition in (
                    (Conversation, Conversation.rider_id == rider_id),
                    (Message, Message.conversation_id.in_(conversation_ids)),
                    (AgentTrace, AgentTrace.conversation_id.in_(conversation_ids)),
                )
            ]
        )


async def test_persistence_continuity_cached_replay_and_no_financial_claim(api):
    client, factory, rider, other = api
    request = payload(rider)
    first = await client.post("/messages", json=request)
    assert first.status_code == 200 and first.json() == {"reply": message_service.AI_REPLY}
    assert (await client.post("/messages", json=request)).json() == first.json()
    assert await counts(factory, rider) == (1, 2, 2)
    assert await counts(factory, other) == (0, 0, 0)
    assert (await client.post("/messages", json=payload(rider))).status_code == 200
    assert await counts(factory, rider) == (1, 4, 4)
    async with factory() as session:
        stored = await session.scalar(
            select(Message).where(Message.message_id == request["message_id"])
        )
        assert stored.content == request["text"] and stored.processing_status == "COMPLETED"
        assert stored.webhook_reply == first.json()["reply"]
        assert stored.received_at == datetime.fromisoformat(request["received_at"])
        assert stored.processing_token is None and stored.processing_expires_at is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PaymentIntent)
                .where(PaymentIntent.rider_id == rider)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(Dispute).where(Dispute.rider_id == rider)
            )
            == 0
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"text": " "},
        {"text": ""},
        {"message_id": " "},
        {"received_at": "2026-09-22T09:05:00"},
        {"received_at": "bad"},
        {"text": "x" * 10001},
        {"unexpected": True},
    ],
)
async def test_invalid_payload(api, changes):
    client, factory, rider, _ = api
    assert (await client.post("/messages", json=payload(rider, **changes))).status_code == 422
    assert await counts(factory, rider) == (0, 0, 0)


async def test_unknown_rider_and_id_conflicts(api):
    client, factory, rider, other = api
    assert (await client.post("/messages", json=payload("missing"))).status_code == 404
    request = payload(rider)
    assert (await client.post("/messages", json=request)).status_code == 200
    for changes in (
        {"text": "different"},
        {"rider_id": other},
        {"received_at": "2026-09-23T09:05:00Z"},
    ):
        assert (await client.post("/messages", json={**request, **changes})).status_code == 409
    assert await counts(factory, rider) == (1, 2, 2)
    assert await counts(factory, other) == (0, 0, 0)


async def test_simultaneous_identical_requests_execute_once(api, monkeypatch):
    client, factory, rider, _ = api
    calls = 0
    entered, release = asyncio.Event(), asyncio.Event()

    async def handler(claim):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return message_service.AI_REPLY

    monkeypatch.setattr(message_service, "deterministic_handler", handler)
    request = payload(rider)
    first = asyncio.create_task(client.post("/messages", json=request))
    await asyncio.wait_for(entered.wait(), 2)
    # Claim remains committed while handler waits; second request sees PROCESSING.
    second = asyncio.create_task(client.post("/messages", json=request))
    await asyncio.sleep(0.1)
    release.set()
    replies = await asyncio.gather(first, second)
    assert all(reply.status_code == 200 for reply in replies)
    assert replies[0].json() == replies[1].json() and calls == 1
    assert await counts(factory, rider) == (1, 2, 2)


async def test_different_first_messages_share_one_conversation(api):
    client, factory, rider, _ = api
    responses = await asyncio.gather(
        *[client.post("/messages", json=payload(rider)) for _ in range(3)]
    )
    assert all(response.status_code == 200 for response in responses)
    assert await counts(factory, rider) == (1, 6, 6)


async def test_expired_lease_recovery_and_stale_owner_cannot_complete(api):
    client, factory, rider, _ = api
    request = payload(rider)
    from app.schemas.messages import IncomingMessage

    claimed = await message_service.claim(factory, IncomingMessage.model_validate(request))
    async with factory() as session, session.begin():
        message = await session.get(Message, claimed.message_id)
        message.processing_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert (await client.post("/messages", json=request)).status_code == 200
    assert (
        await message_service.complete(factory, claimed, "must never replace cached reply")
        == message_service.AI_REPLY
    )
    assert await counts(factory, rider) == (1, 2, 2)


async def test_failed_handler_recovers_on_retry(api, monkeypatch):
    client, factory, rider, _ = api
    request = payload(rider)

    async def fail(claim):
        raise RuntimeError("private-password")

    monkeypatch.setattr(message_service, "deterministic_handler", fail)
    failed = await client.post("/messages", json=request)
    assert failed.status_code == 503 and failed.headers["retry-after"] == "1"
    assert "private-password" not in failed.text
    async with factory() as session:
        message = await session.scalar(
            select(Message).where(Message.message_id == request["message_id"])
        )
        assert message.processing_status == "FAILED" and message.webhook_reply is None
    monkeypatch.setattr(
        message_service,
        "deterministic_handler",
        lambda claim: asyncio.sleep(0, result=message_service.AI_REPLY),
    )
    assert (await client.post("/messages", json=request)).status_code == 200
    assert await counts(factory, rider) == (1, 2, 3)  # incoming, error, final reply


async def test_human_mode_has_no_simulated_ai_reply_and_resolved_stays_closed(api):
    client, factory, rider, _ = api
    assert (await client.post("/messages", json=payload(rider))).status_code == 200
    async with factory() as session, session.begin():
        conversation = await session.scalar(
            select(Conversation).where(Conversation.rider_id == rider)
        )
        identifier = conversation.id
        conversation.handling_mode = "HUMAN"
        conversation.status = "HUMAN_HANDLING"
    response = await client.post("/messages", json=payload(rider))
    assert response.json()["reply"] == message_service.HUMAN_REPLY
    assert await counts(factory, rider) == (1, 3, 4)
    async with factory() as session, session.begin():
        conversation = await session.get(Conversation, identifier)
        conversation.status = "RESOLVED"
    assert (await client.post("/messages", json=payload(rider))).status_code == 200
    assert await counts(factory, rider) == (2, 5, 6)
    async with factory() as session:
        assert (await session.get(Conversation, identifier)).status == "RESOLVED"


async def test_audit_chronology_redaction_and_rider_isolation(api):
    client, factory, rider, other = api
    assert (await client.get(f"/trace/{rider}")).json() == []
    assert (await client.get("/trace/missing")).status_code == 404
    assert (await client.post("/messages", json=payload(rider))).status_code == 200
    async with factory() as session, session.begin():
        conversation = await session.scalar(
            select(Conversation).where(Conversation.rider_id == rider)
        )
        timestamp = datetime.now(UTC)
        for _ in range(2):
            trace_service.record(
                session,
                conversation.id,
                "tool_call",
                "actual_test_tool",
                input={
                    "password": "secret",
                    "nested": {"api_key": "private"},
                    "amount": Decimal("1.25"),
                },
                output={"id": uuid4(), "at": timestamp, "chain_of_thought": "private"},
                at=timestamp,
            )
    first = await client.get(f"/trace/{rider}")
    second = await client.get(f"/trace/{rider}")
    assert first.json() == second.json()
    events = first.json()
    assert events[0]["type"] == "message_in" and events[1]["type"] == "reply"
    assert [event["at"] for event in events] == sorted(event["at"] for event in events)
    assert events[-1]["input"]["amount"] == "1.25"
    assert events[-1]["input"]["nested"]["api_key"] == "[REDACTED]"
    assert events[-1]["output"]["chain_of_thought"] == "[REDACTED]"
    assert (await client.get(f"/trace/{other}")).json() == []


async def test_rider_read_pagination_scope_and_internal_notes(api):
    client, factory, rider, other = api
    assert (await client.post("/messages", json=payload(rider))).status_code == 200
    listing = await client.get(f"/ui/riders/{rider}/conversations?limit=1")
    assert listing.status_code == 200 and listing.json()["total"] == 1
    conversation = listing.json()["items"][0]
    identifier = conversation["id"]
    async with factory() as session, session.begin():
        session.add(
            Message(
                conversation_id=UUID(identifier),
                sender_type="OPS",
                content="private note",
                is_internal=True,
            )
        )
    assert (await client.get(f"/ui/conversations/{identifier}", params={"rider_id": rider})).json()[
        "handler"
    ] == "AI"
    assert (
        await client.get(f"/ui/conversations/{identifier}", params={"rider_id": other})
    ).status_code == 404
    for suffix in ("messages", "disputes"):
        assert (
            await client.get(f"/ui/conversations/{identifier}/{suffix}", params={"rider_id": other})
        ).status_code == 404
        assert (
            await client.get(f"/ui/conversations/{uuid4()}/{suffix}", params={"rider_id": rider})
        ).status_code == 404
    response = await client.get(
        f"/ui/conversations/{identifier}/messages",
        params={"rider_id": rider, "limit": 1, "offset": 1},
    )
    assert response.json()["total"] == 2 and len(response.json()["items"]) == 1
    assert (
        await client.get(f"/ui/conversations/{identifier}/disputes", params={"rider_id": rider})
    ).json()["items"] == []
    assert (await client.get(f"/ui/conversations/{identifier}/messages")).status_code == 422
    assert (await client.get(f"/ui/ops/conversations/{identifier}")).json()["messages"][
        "total"
    ] == 3


async def test_pending_queue_and_internal_ops_reads(api):
    client, factory, rider, _ = api
    assert (await client.get("/ops/pending")).json() == []
    empty = (await client.get("/ui/ops/overview")).json()
    assert empty["pending_approvals"] == 0 and empty["confirmed_payment_amount"] == "0"
    assert (await client.post("/messages", json=payload(rider))).status_code == 200
    async with factory() as session, session.begin():
        conversation = await session.scalar(
            select(Conversation).where(Conversation.rider_id == rider)
        )
        dispute = Dispute(
            conversation_id=conversation.id,
            rider_id=rider,
            status="AWAITING_APPROVAL",
            verified_amount=Decimal(425),
        )
        session.add(dispute)
        await session.flush()
        session.add(
            DisputeItem(
                dispute_id=dispute.id,
                source_type="trip",
                source_id="test-trip",
                expected_amount=Decimal(65),
                actual_amount=Decimal(43),
                difference=Decimal(22),
            )
        )
        for index, status in enumerate(
            ("PENDING", "IN_REVIEW", "APPROVED", "REJECTED", "RESOLVED")
        ):
            session.add(
                OpsQueue(
                    dispute_id=dispute.id,
                    type="approval" if index % 2 == 0 else "escalation",
                    status=status,
                    amount=Decimal(425),
                    reason="Test pending reason",
                )
            )
        # Resolved timestamp excludes an inconsistent pending row as well.
        session.add(
            OpsQueue(
                dispute_id=dispute.id,
                type="approval",
                status="PENDING",
                amount=Decimal(425),
                reason="Already resolved",
                resolved_at=datetime.now(UTC),
            )
        )
        payout = PaymentIntent(
            dispute_id=dispute.id,
            rider_id=rider,
            amount=Decimal(425),
            payment_type="OPS_APPROVED",
            idempotency_key=uuid4().hex,
            status="SUCCEEDED",
            provider_payout_id="test-provider",
            last_reconciled_at=datetime.now(UTC),
        )
        session.add(payout)
        await session.flush()
        payout_id = payout.id
    pending = (await client.get("/ops/pending")).json()
    assert len(pending) == 2
    assert {item["type"] for item in pending} == {"approval", "escalation"}
    assert all(
        set(item) == {"id", "rider_id", "type", "amount", "reason", "created_at"}
        for item in pending
    )
    assert next(item for item in pending if item["type"] == "approval")["amount"] == 425
    assert next(item for item in pending if item["type"] == "escalation")["amount"] is None
    metrics = (await client.get("/ui/ops/overview")).json()
    assert metrics["pending_approvals"] == 1 and metrics["open_escalations"] == 1
    assert metrics["confirmed_payment_amount"] == "425"
    cases = (
        await client.get(
            "/ui/ops/cases", params={"rider_id": rider, "status": "PENDING", "limit": 1}
        )
    ).json()
    assert cases["total"] == 2
    assert (await client.get(f"/ui/ops/cases/{pending[0]['id']}")).status_code == 200
    payouts = (
        await client.get("/ui/ops/payouts", params={"rider_id": rider, "status": "SUCCEEDED"})
    ).json()
    assert payouts["total"] == 1 and payouts["items"][0]["amount_rupees"] == "425"
    assert "idempotency_key" not in payouts["items"][0]
    assert (await client.get(f"/ui/ops/payouts/{payout_id}")).status_code == 200
    threads = (
        await client.get(
            "/ui/ops/conversations",
            params={"rider_id": rider, "handling_mode": "AI", "status": "OPEN"},
        )
    ).json()
    assert threads["total"] == 1
    details = (await client.get(f"/ui/ops/conversations/{conversation.id}")).json()
    assert details["disputes"]["total"] == 1
    evidence = (
        await client.get(
            f"/ui/conversations/{conversation.id}/disputes", params={"rider_id": rider}
        )
    ).json()
    assert evidence["items"][0]["items"][0]["difference"] == "22"
    trace = (
        await client.get("/ui/ops/traces", params={"rider_id": rider, "type": "reply", "limit": 1})
    ).json()
    assert trace["total"] == 1 and trace["items"][0]["rider_id"] == rider
    for collection in ("cases", "payouts", "conversations"):
        assert (await client.get(f"/ui/ops/{collection}/{uuid4()}")).status_code == 404
    assert (await client.post("/ui/ops/cases", json={})).status_code == 405


async def test_busy_request_returns_retryable_503_without_final_cache(api, monkeypatch):
    from app.schemas.messages import IncomingMessage

    client, factory, rider, _ = api
    request = payload(rider)
    await message_service.claim(factory, IncomingMessage.model_validate(request))
    monkeypatch.setattr(message_service, "WEBHOOK_TIMEOUT_SECONDS", 0.05)
    response = await client.post("/messages", json=request)
    assert response.status_code == 503 and response.headers["retry-after"] == "1"
    async with factory() as session:
        message = await session.scalar(
            select(Message).where(Message.message_id == request["message_id"])
        )
        assert message.processing_status == "PROCESSING" and message.webhook_reply is None
    assert await counts(factory, rider) == (1, 1, 1)


async def test_stale_owner_cannot_finish_after_lease_reclaimed(api):
    from app.schemas.messages import IncomingMessage

    _, factory, rider, _ = api
    request = IncomingMessage.model_validate(payload(rider))
    old = await message_service.claim(factory, request)
    async with factory() as session, session.begin():
        message = await session.get(Message, old.message_id)
        message.processing_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    current = await message_service.claim(factory, request)
    assert current.token != old.token
    with pytest.raises(message_service.ProcessingBusy):
        await message_service.complete(factory, old, "stale reply")
    await message_service.complete(factory, current, message_service.AI_REPLY)
    assert await counts(factory, rider) == (1, 2, 2)


async def test_reply_and_trace_rollback_together(api, monkeypatch):
    client, factory, rider, _ = api
    request = payload(rider)
    original = trace_service.record

    def reject_reply(session, conversation_id, event_type, name, **values):
        if event_type == "reply":
            raise RuntimeError("force transaction rollback")
        return original(session, conversation_id, event_type, name, **values)

    monkeypatch.setattr(trace_service, "record", reject_reply)
    assert (await client.post("/messages", json=request)).status_code == 503
    assert await counts(factory, rider) == (1, 1, 2)
    monkeypatch.setattr(trace_service, "record", original)
    assert (await client.post("/messages", json=request)).status_code == 200
    assert await counts(factory, rider) == (1, 2, 3)


async def test_simultaneous_conflicting_requests_do_not_duplicate(api):
    client, factory, rider, _ = api
    request = payload(rider)
    replies = await asyncio.gather(
        client.post("/messages", json=request),
        client.post("/messages", json={**request, "text": "conflicting content"}),
    )
    assert sorted(reply.status_code for reply in replies) == [200, 409]
    assert await counts(factory, rider) == (1, 2, 2)
