"""Transient event safety, real Redis fan-out, HTTP authorization, and stream cleanup."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from test_ops_endpoints import conversation, login
from test_ops_endpoints import ops_api as ops_api
from test_payments_database import provider as provider

from app.api import realtime
from app.core.config import get_settings
from app.models import Conversation, Message
from app.realtime import publisher
from app.realtime.events import EventData, LiveEvent
from app.realtime.subscriber import subscribe

real_publish = publisher.publish
pytestmark = pytest.mark.database


def live(kind="agent.status", **data):
    return LiveEvent(
        event_type=kind, conversation_id=uuid4(), rider_id="R003", data=EventData(**data)
    )


def test_event_roundtrip_and_explicit_payload():
    from pydantic import ValidationError

    event = live(status="checking_trip_records")
    assert LiveEvent.model_validate_json(event.model_dump_json()) == event
    assert f"event: {event.event_type}\n" in event.sse()
    assert f"id: {event.event_id}\n" in event.sse()
    assert event.timestamp.tzinfo is not None
    with pytest.raises(ValidationError):
        EventData(password="must never be published")
    with pytest.raises(ValidationError):
        EventData(chain_of_thought="private")


async def test_real_redis_fans_out_to_two_subscribers():
    event = live(status="checking_trip_records")
    channel = f"quickdrop:conversation:{event.conversation_id}"
    async with Redis.from_url(get_settings().redis_url.get_secret_value()) as redis:
        assert await redis.ping()
    async with subscribe(channel) as first, subscribe(channel) as second:
        await real_publish(event)

        async def receive(subscription):
            async with asyncio.timeout(3):
                while True:
                    message = await subscription.get_message(
                        ignore_subscribe_messages=True, timeout=1
                    )
                    if message:
                        return LiveEvent.model_validate_json(message["data"])

        assert await receive(first) == event
        assert await receive(second) == event


async def test_publisher_failure_is_best_effort(monkeypatch):
    from app.realtime import publisher as module

    class Unavailable:
        async def __aenter__(self):
            raise ConnectionError("Redis unavailable")

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(module.Redis, "from_url", lambda *a, **k: Unavailable())
    await real_publish(live(status="saved"))


async def test_sse_named_frames_heartbeat_and_disconnect_cleanup(monkeypatch):
    event = live(status="checking_trip_records")
    state = {"closed": False, "calls": 0}
    pubsub = SimpleNamespace(
        get_message=AsyncMock(side_effect=[{"data": event.model_dump_json()}, None])
    )

    @asynccontextmanager
    async def fake_subscribe(channel):
        try:
            yield pubsub
        finally:
            state["closed"] = True

    async def disconnected():
        state["calls"] += 1
        return state["calls"] > 2

    monkeypatch.setattr(realtime, "subscribe", fake_subscribe)
    frames = [
        frame
        async for frame in realtime.stream(SimpleNamespace(is_disconnected=disconnected), "channel")
    ]
    assert frames[0].startswith("retry:")
    assert "event: ready" in frames[1]
    assert "event: agent.status" in frames[2]
    assert frames[3] == ": heartbeat\n\n"
    assert state["closed"]


async def test_sse_cancellation_closes_subscription(monkeypatch):
    state = {"closed": False}
    entered = asyncio.Event()

    async def wait(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    @asynccontextmanager
    async def fake_subscribe(channel):
        try:
            yield SimpleNamespace(get_message=wait)
        finally:
            state["closed"] = True

    monkeypatch.setattr(realtime, "subscribe", fake_subscribe)

    async def consume():
        async for _ in realtime.stream(
            SimpleNamespace(is_disconnected=AsyncMock(return_value=False)), "channel"
        ):
            pass

    task = asyncio.create_task(consume())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert state["closed"]


async def test_sse_redis_unavailable_and_session_expiration(monkeypatch):
    @asynccontextmanager
    async def unavailable(channel):
        raise ConnectionError("offline")
        yield

    monkeypatch.setattr(realtime, "subscribe", unavailable)
    frames = [
        f
        async for f in realtime.stream(
            SimpleNamespace(is_disconnected=AsyncMock(return_value=False)), "channel"
        )
    ]
    assert "unavailable" in frames[-1]

    @asynccontextmanager
    async def available(channel):
        yield SimpleNamespace()

    monkeypatch.setattr(realtime, "subscribe", available)
    frames = [
        f
        async for f in realtime.stream(
            SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
            "channel",
            session_valid=AsyncMock(return_value=False),
        )
    ]
    assert "session.expired" in frames[-1]


async def test_signed_rider_context_and_cross_rider_subscription(ops_api):
    e = ops_api
    identifier = await conversation(e)
    url = f"/ui/conversations/{identifier}/events?rider_id={e.rider}"
    assert (await e.http.get(url)).status_code == 401
    assert (await e.http.get("/ui/ops/events")).status_code == 401
    assert (await e.http.post("/ui/demo/rider", json={"rider_id": e.rider})).status_code == 200
    assert (
        await e.http.get(f"/ui/conversations/{uuid4()}/events?rider_id={e.rider}")
    ).status_code == 404
    assert (await e.http.get(url.replace(e.rider, "R999"))).status_code == 401
    assert (await e.http.post("/ui/demo/rider", json={"rider_id": "R999"})).status_code == 404
    assert (
        await e.http.post(
            "/ui/demo/rider", json={"rider_id": e.rider}, headers={"Origin": "https://evil.invalid"}
        )
    ).status_code == 403


async def test_committed_events_and_rollback_never_publish_early(ops_api):
    e = ops_api
    publisher.publish.reset_mock()
    async with e.factory() as session:
        row = Conversation(rider_id=e.rider)
        session.add(row)
        await session.flush()
        assert not publisher.publish.called
        await session.commit()
    await publisher.drain()
    assert publisher.publish.await_count == 1
    publisher.publish.reset_mock()
    async with e.factory() as session:
        session.add(Conversation(rider_id=e.rider))
        await session.flush()
        await session.rollback()
    await publisher.drain()
    assert not publisher.publish.called


async def test_human_message_events_are_public_and_notes_ops_only(ops_api):
    e = ops_api
    await login(e)
    identifier = await conversation(e)
    base = f"/ui/ops/conversations/{identifier}"
    await e.http.post(base + "/takeover")
    await publisher.drain()
    publisher.publish.reset_mock()
    assert (
        await e.http.post(
            base + "/notes", json={"text": "Confidential note", "client_request_id": str(uuid4())}
        )
    ).status_code == 201
    await publisher.drain()
    events = publisher.publish.await_args_list
    notes = [c for c in events if c.args[0].event_type == "message.created"]
    assert len(notes) == 1 and notes[0].kwargs["internal"]
    assert all("Confidential note" not in c.args[0].model_dump_json() for c in events)
    publisher.publish.reset_mock()
    assert (
        await e.http.post(
            base + "/messages", json={"text": "Support reply", "client_request_id": str(uuid4())}
        )
    ).status_code == 201
    await publisher.drain()
    replies = [
        c for c in publisher.publish.await_args_list if c.args[0].event_type == "message.created"
    ]
    assert len(replies) == 1 and not replies[0].kwargs["internal"]


async def test_safe_final_text_has_stable_identity_and_no_model_output(ops_api):
    e = ops_api
    identifier = await conversation(e)
    async with e.factory() as session, session.begin():
        message = Message(
            conversation_id=identifier, sender_type="AI", content="Verified reply for rider"
        )
        session.add(message)
        await session.flush()
        mid = message.id
    await publisher.drain()
    events = [
        c.args[0]
        for c in publisher.publish.await_args_list
        if c.args[0].event_type.startswith("agent.message.")
    ]
    assert [x.event_type for x in events] == ["agent.message.delta", "agent.message.completed"]
    assert {x.data.message_id for x in events} == {mid}
    assert len({x.run_id for x in events}) == 1
    assert events[0].sequence < events[1].sequence
    assert events[0].data.text == "Verified reply for rider"


async def test_committed_reply_streams_multiple_exact_chunks(ops_api):
    e = ops_api
    identifier = await conversation(e)
    await publisher.drain()
    publisher.publish.reset_mock()
    text = "Verified source records. " * 12
    async with e.factory() as session:
        row = Message(conversation_id=identifier, sender_type="AI", content=text)
        session.add(row)
        await session.flush()
        assert not publisher.publish.called
        await session.commit()
    await publisher.drain()
    events = [call.args[0] for call in publisher.publish.await_args_list]
    chunks = [event for event in events if event.event_type == "agent.message.delta"]
    assert len(chunks) > 1
    assert "".join(event.data.text for event in chunks) == text
    assert {event.data.message_id for event in chunks} == {row.id}
    completed = next(event for event in events if event.event_type == "agent.message.completed")
    assert completed.data.text == text and completed.sequence > chunks[-1].sequence


async def test_signed_simulator_reads_and_explicit_thread_submission(ops_api, monkeypatch):
    e = ops_api
    assert (await e.http.post("/ui/demo/rider", json={"rider_id": e.rider})).status_code == 200
    first = await e.http.post(f"/ui/riders/{e.rider}/conversations")
    second = await e.http.post(f"/ui/riders/{e.rider}/conversations")
    assert first.status_code == second.status_code == 200
    identifier = first.json()["id"]
    monkeypatch.setattr(
        "app.services.message_service.run_handler", AsyncMock(return_value="Persisted reply")
    )
    payload = {
        "message_id": uuid4().hex,
        "rider_id": e.rider,
        "text": "Issue in the older thread",
        "received_at": "2026-09-23T09:05:00Z",
        "conversation_id": identifier,
    }
    response = await e.http.post("/messages", json=payload)
    assert response.status_code == 200 and response.json() == {"reply": "Persisted reply"}
    history = await e.http.get(
        f"/ui/conversations/{identifier}/messages", params={"rider_id": e.rider}
    )
    assert history.json()["total"] == 2
    assert history.json()["items"][0]["client_message_id"] == payload["message_id"]
    payouts = await e.http.get(
        f"/ui/conversations/{identifier}/payouts", params={"rider_id": e.rider}
    )
    assert payouts.status_code == 200 and payouts.json()["total"] == 0


async def test_authorized_http_sse_responses(ops_api, monkeypatch):
    e = ops_api
    identifier = await conversation(e)
    await e.http.post("/ui/demo/rider", json={"rider_id": e.rider})
    event = LiveEvent(
        event_type="conversation.updated",
        conversation_id=identifier,
        rider_id=e.rider,
        data=EventData(status="OPEN"),
    )

    async def finite_stream(*args, **kwargs):
        yield "retry: 2000\n\n"
        yield event.sse()

    monkeypatch.setattr(realtime, "stream", finite_stream)
    response = await e.http.get(
        f"/ui/conversations/{identifier}/events", params={"rider_id": e.rider}
    )
    assert response.status_code == 200 and response.headers["content-type"].startswith(
        "text/event-stream"
    )
    assert response.headers["x-accel-buffering"] == "no"
    assert "event: conversation.updated" in response.text
    await login(e)
    assert (await e.http.get("/ui/ops/events")).status_code == 200


async def test_worker_payment_events_follow_provider_confirmation(ops_api, monkeypatch):
    from uuid import UUID

    from test_ops_endpoints import financial_case

    from app.services import ops_case_service
    from app.services.payment_worker import process_one, reconcile_intent

    e = ops_api
    await login(e)
    case, _, _ = await financial_case(e)
    monkeypatch.setattr(ops_case_service, "source_coverage", AsyncMock(return_value=True))
    approval = await e.http.post(f"/ui/ops/cases/{case}/approve")
    assert approval.status_code == 200
    await publisher.drain()
    pending = [
        c.args[0]
        for c in publisher.publish.await_args_list
        if c.args[0].event_type == "payment.status_changed"
    ]
    assert pending[-1].data.status == "PENDING" and not e.mock.posts
    assert await process_one(e.factory, e.client)
    await publisher.drain()
    completed = [
        c.args[0]
        for c in publisher.publish.await_args_list
        if c.args[0].event_type == "payment.status_changed"
    ]
    assert completed[-1].data.status == "SUCCEEDED"
    assert len(e.mock.posts) == 1
    assert (
        await reconcile_intent(e.factory, e.client, UUID(approval.json()["payment_intent_id"]))
        == "SUCCEEDED"
    )
    await publisher.drain()
    assert any(
        c.args[0].event_type == "payment.reconciled" for c in publisher.publish.await_args_list
    )


@pytest.mark.parametrize("amount", [25, 425])
async def test_complete_rider_ops_worker_flow_with_real_redis(ops_api, monkeypatch, amount):
    """Full HTTP/service flow, isolated PostgreSQL, two Redis subscribers, mock provider only."""
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.agent import llm
    from app.agent.state import Extraction
    from app.agent.tools import investigation
    from app.models import PayoutLine, Trip
    from app.repositories.trips import IST
    from app.services import ops_case_service
    from app.services.payment_worker import process_one

    e = ops_api
    trip_id = "T" + str(uuid4().int)[:16]
    # These cases create trips relative to real now; explicitly exercise the unset clock.
    monkeypatch.setattr("app.core.clock.get_settings", lambda: e.settings)
    now = datetime.now(UTC)
    day = now.astimezone(IST).date() - timedelta(days=1)
    async with e.factory() as session, session.begin():
        session.add(
            Trip(
                trip_id=trip_id,
                rider_id=e.rider,
                status="completed",
                started_at=datetime.combine(day, datetime.min.time(), IST) + timedelta(hours=12),
                distance_km=Decimal(2) + Decimal(amount) / Decimal(6),
                surge_multiplier=Decimal(1),
            )
        )
        await session.flush()
        session.add(
            PayoutLine(
                line_id="L" + uuid4().hex[:20],
                rider_id=e.rider,
                trip_id=trip_id,
                payout_date=day,
                line_type="trip",
                amount=Decimal(25),
            )
        )
    monkeypatch.setattr(investigation, "source_coverage", AsyncMock(return_value=True))
    monkeypatch.setattr(ops_case_service, "source_coverage", AsyncMock(return_value=True))
    monkeypatch.setattr(investigation, "get_payswift_client", lambda: e.client)
    monkeypatch.setattr(
        llm,
        "extract",
        AsyncMock(
            return_value=Extraction(
                intent="complaint",
                language="en",
                claims=[{"kind": "PAYOUT", "trip_ids": [trip_id]}],
            )
        ),
    )
    monkeypatch.setattr(publisher, "publish", real_publish)
    assert (await e.http.post("/ui/demo/rider", json={"rider_id": e.rider})).status_code == 200
    created = await e.http.post(f"/ui/riders/{e.rider}/conversations")
    identifier = created.json()["id"]
    async with (
        subscribe(f"quickdrop:conversation:{identifier}") as rider_events,
        subscribe("quickdrop:ops:events") as ops_events,
    ):
        submitted = await e.http.post(
            "/messages",
            json={
                "message_id": uuid4().hex,
                "rider_id": e.rider,
                "conversation_id": identifier,
                "text": f"Payment missing for {trip_id}",
                "received_at": now.isoformat(),
            },
        )
        assert submitted.status_code == 200 and str(amount) in submitted.json()["reply"]
        state = await e.http.get(f"/ui/riders/{e.rider}/conversations")
        assert state.status_code == 200
        current = next(c for c in state.json()["items"] if c["id"] == identifier)
        assert current["status"] == ("PAYMENT_PENDING" if amount <= 200 else "AWAITING_APPROVAL")
        await login(e)
        thread = await e.http.get(f"/ui/ops/conversations/{identifier}")
        assert thread.status_code == 200 and thread.json()["messages"]["total"] == 2
        base = f"/ui/ops/conversations/{identifier}"
        assert (await e.http.post(base + "/takeover")).status_code == 200
        assert (
            await e.http.post(
                base + "/messages",
                json={"text": "I have reviewed your claim", "client_request_id": str(uuid4())},
            )
        ).status_code == 201
        assert (
            await e.http.post(
                base + "/notes",
                json={"text": "Private review note", "client_request_id": str(uuid4())},
            )
        ).status_code == 201
        cases = await e.http.get("/ui/ops/cases", params={"rider_id": e.rider})
        if amount > 200:
            case = cases.json()["items"][0]
            assert case["amount"] == amount and case["type"] == "approval"
            approval = await e.http.post(f"/ui/ops/cases/{case['id']}/approve")
            assert approval.status_code == 200 and not approval.json()["payment_confirmed"]
        else:
            assert cases.json()["items"] == []
        assert not e.mock.posts
        assert await process_one(e.factory, e.client)
        await publisher.drain()
        history = await e.http.get(
            f"/ui/conversations/{identifier}/messages", params={"rider_id": e.rider}
        )
        assert history.json()["total"] == 3 and "Private review note" not in history.text
        payout = await e.http.get(
            f"/ui/conversations/{identifier}/payouts", params={"rider_id": e.rider}
        )
        assert payout.json()["items"][0]["status"] == "SUCCEEDED"

        async def received(subscription):
            events = []
            async with asyncio.timeout(4):
                while True:
                    message = await subscription.get_message(
                        ignore_subscribe_messages=True, timeout=0.2
                    )
                    if message:
                        events.append(LiveEvent.model_validate_json(message["data"]))
                    elif events:
                        return events

        rider = await received(rider_events)
        operator = await received(ops_events)
        progress = [x.data.status for x in rider if x.event_type == "agent.status"]
        expected_progress = [
            "understanding_complaint",
            "checking_trip_records",
            "retrieving_payout_history",
            "calculating_verified_shortfall",
            "checking_payment_eligibility",
            "authorizing_payment",
            "preparing_response",
        ]
        assert progress == expected_progress
        finals = [x for x in rider if x.event_type == "agent.message.completed"]
        assert len(finals) == 1 and finals[0].data.text == submitted.json()["reply"]
        statuses = [x.data.status for x in rider if x.event_type == "payment.status_changed"]
        assert "PENDING" in statuses and statuses[-1] == "SUCCEEDED"
        assert any(x.event_type == "message.created" and x.data.sender == "OPS" for x in rider)
        assert len(operator) > len(rider)
