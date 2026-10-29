import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from test_agent_graph import agent_setup as agent_setup
from test_messaging import api as api
from test_payments_database import provider as provider

from app.agent import llm
from app.agent.graph import run_agent
from app.agent.state import Extraction
from app.agent.tools import investigation
from app.core.database import get_session_factory
from app.main import create_app
from app.models import AgentTrace, Conversation, Message, OpsQueue, PaymentIntent
from app.services import message_service

pytestmark = pytest.mark.database


def request(rider="R003", text="T926334 surge missing"):
    return {
        "message_id": "webhook." + uuid4().hex,
        "rider_id": rider,
        "text": text,
        "received_at": "2026-09-22T09:05:00+05:30",
    }


async def ready(factory):
    async with factory() as session, session.begin():
        messages = list(
            await session.scalars(select(Message).where(Message.processing_status == "RECEIVED"))
        )
        for message in messages:
            message.next_processing_at = datetime.now(UTC) - timedelta(seconds=1)


async def test_complete_messages_endpoint_with_real_graph(agent_setup, monkeypatch):
    factory, _, client = agent_setup
    model = AsyncMock(
        return_value=Extraction(
            intent="complaint",
            language="en",
            claims=[{"kind": "SURGE", "trip_ids": ["T926334"], "date_tokens": ["20"]}],
        )
    )
    monkeypatch.setattr(llm, "extract", model)
    monkeypatch.setattr(investigation, "get_payswift_client", lambda: client)
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    payload = request(text="Bhai order T926334 ka surge nahi mila, 20 tarikh wala. Check karo pls")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        first = await http.post("/messages", json=payload)
        again = await http.post("/messages", json=payload)
        assert first.status_code == 200 and first.json() == again.json()
        assert "25" in first.json()["reply"] and "confirm nahi" in first.json()["reply"]
    assert model.await_count == 1
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(PaymentIntent)) == 1
        assert await session.scalar(select(func.count()).select_from(Message)) == 2
        message = await session.scalar(
            select(Message).where(Message.message_id == payload["message_id"])
        )
        assert message.received_at == datetime.fromisoformat(payload["received_at"])
        intent = await session.scalar(select(PaymentIntent))
        assert intent.status == "PENDING" and intent.payment_type == "AUTO"
        assert datetime.fromisoformat(
            intent.authorization["request"]["received_at"]
        ) == datetime.fromisoformat(payload["received_at"])
        assert not list(await session.scalars(select(OpsQueue)))
    from app.services.payment_worker import process_one

    assert await process_one(factory, client)
    assert not await process_one(factory, client)
    async with factory() as session:
        intent = await session.scalar(select(PaymentIntent))
        assert intent.status == "SUCCEEDED" and intent.provider_payout_id


async def test_deadline_ack_is_durable_and_resumes(agent_setup, monkeypatch):
    factory, _, client = agent_setup
    entered = asyncio.Event()

    async def slow(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(llm, "extract", slow)
    monkeypatch.setattr(investigation, "get_payswift_client", lambda: client)
    monkeypatch.setattr(
        message_service,
        "get_settings",
        lambda: SimpleNamespace(
            agent_foreground_seconds=0.5, agent_job_seconds=24, agent_max_attempts=3
        ),
    )
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    payload = request()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        pending = await http.post("/messages", json=payload)
        assert entered.is_set() and pending.status_code == 200
        assert pending.json()["reply"] == message_service.PENDING_REPLY
        assert (await http.post("/messages", json=payload)).json() == pending.json()
        async with factory() as session:
            message = await session.scalar(
                select(Message).where(Message.message_id == payload["message_id"])
            )
            assert message.processing_status == "RECEIVED" and message.processing_token is None
        monkeypatch.setattr(
            llm,
            "extract",
            AsyncMock(
                return_value=Extraction(
                    intent="complaint",
                    language="en",
                    claims=[{"kind": "SURGE", "trip_ids": ["T926334"]}],
                )
            ),
        )
        await ready(factory)
        assert await message_service.resume_one(factory)
        final = await http.post("/messages", json=payload)
        assert "25" in final.json()["reply"] and final.json() != pending.json()
    async with factory() as session:
        message = await session.scalar(
            select(Message).where(Message.message_id == payload["message_id"])
        )
        assert message.processing_status == "COMPLETED" and message.agent_attempts == 2
        assert await session.scalar(select(func.count()).select_from(PaymentIntent)) == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(AgentTrace).where(AgentTrace.type == "message_in")
            )
            == 1
        )


async def test_persistent_llm_failure_escalates_after_bounded_attempts(agent_setup, monkeypatch):
    factory, _, client = agent_setup
    monkeypatch.setattr(
        llm, "extract", AsyncMock(side_effect=llm.ExtractionUnavailable("RateLimitError"))
    )
    monkeypatch.setattr(investigation, "get_payswift_client", lambda: client)
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    payload = request()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        assert (await http.post("/messages", json=payload)).status_code == 200
        for _ in range(3):
            await ready(factory)
            assert await message_service.resume_one(factory)
        final = await http.post("/messages", json=payload)
        assert "support review" in final.json()["reply"]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(OpsQueue)) == 1
        assert not list(await session.scalars(select(PaymentIntent)))


async def test_human_mode_bypasses_model(agent_setup, monkeypatch):
    factory, turn, client = agent_setup
    _, claimed, _, _ = await turn("R003", "hello", {"intent": "other", "language": "en"})
    async with factory() as session, session.begin():
        conversation = await session.get(Conversation, claimed.conversation_id)
        conversation.handling_mode, conversation.status = "HUMAN", "HUMAN_HANDLING"
    model = AsyncMock(side_effect=AssertionError("HUMAN mode must not invoke LLM"))
    monkeypatch.setattr(llm, "extract", model)
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.post("/messages", json=request())
        assert response.json()["reply"] == message_service.HUMAN_REPLY
    model.assert_not_awaited()


async def test_real_graph_concurrent_webhook_has_one_execution(api, monkeypatch):
    http, factory, rider, _ = api
    entered, release = asyncio.Event(), asyncio.Event()
    model = AsyncMock()

    async def extraction(**kwargs):
        entered.set()
        await release.wait()
        return Extraction(intent="complaint", language="en", claims=[{"kind": "PAYOUT"}])

    model.side_effect = extraction

    async def handler(factory, claimed):
        return await run_agent(factory, claimed, extractor=model)

    monkeypatch.setattr(message_service, "run_handler", handler)
    payload = request(rider, "payout wrong")
    first = asyncio.create_task(http.post("/messages", json=payload))
    await asyncio.wait_for(entered.wait(), 2)
    second = asyncio.create_task(http.post("/messages", json=payload))
    await asyncio.sleep(0.05)
    release.set()
    responses = await asyncio.gather(first, second)
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json() and model.await_count == 1
