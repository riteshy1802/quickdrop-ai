"""A settled financial dispute does not close rider support or create another payment."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from test_agent_graph import agent_setup as agent_setup
from test_agent_graph import extracted
from test_payments_database import provider as provider

from app.agent import llm
from app.agent.state import Extraction
from app.agent.tools import investigation
from app.core.database import get_db_session, get_session_factory
from app.main import create_app
from app.models import Conversation, Dispute, Message, OpsQueue, PaymentIntent
from app.realtime import publisher
from app.services.payment_worker import process_one, reconcile_intent

pytestmark = pytest.mark.database


async def test_r033_paid_dispute_accepts_same_thread_status_followup(agent_setup, monkeypatch):
    factory, turn, client = agent_setup
    _, first, _, payload = await turn(
        "R033",
        "20 tarikh ke 2 order ka payment nahi aaya: T795007, T206956",
        extracted("PAYOUT", ids=("T795007", "T206956"), dates=("20",)),
    )
    async with factory() as session:
        assert (await session.get(Conversation, first.conversation_id)).status != "RESOLVED"
    await publisher.drain()
    publisher.publish.reset_mock()
    assert await process_one(factory, client)
    await publisher.drain()
    events = [call.args[0] for call in publisher.publish.await_args_list]
    assert any(
        event.event_type == "dispute.updated" and event.data.status == "RESOLVED"
        for event in events
    )
    assert any(
        event.event_type == "payment.status_changed" and event.data.status == "SUCCEEDED"
        for event in events
    )
    assert not any(
        event.event_type == "conversation.updated" and event.data.status == "RESOLVED"
        for event in events
    )
    async with factory() as session:
        intent = await session.scalar(select(PaymentIntent))
        assert intent.amount == 176 and intent.status == "SUCCEEDED"
        assert (await session.get(Dispute, intent.dispute_id)).status == "RESOLVED"
        conversation = await session.get(Conversation, first.conversation_id)
        assert conversation.status == "OPEN"
        before_context = conversation.context["agent"]["dispute_ids"]
    monkeypatch.setattr(
        llm, "extract", AsyncMock(return_value=Extraction(intent="status", language="hinglish"))
    )
    monkeypatch.setattr(investigation, "get_payswift_client", lambda: client)
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory

    async def isolated_session():
        async with factory() as session:
            yield session

    # Rider selection uses Session, whereas /messages uses the factory dependency.
    # Both must see the same uncommitted fixture data, never the default database.
    app.dependency_overrides[get_db_session] = isolated_session
    monkeypatch.setattr(
        "app.core.database.get_session_factory",
        Mock(side_effect=AssertionError("HTTP test accessed the default database")),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        assert (await http.post("/ui/demo/rider", json={"rider_id": "R033"})).status_code == 200
        followup = {
            "message_id": "followup." + uuid4().hex,
            "rider_id": "R033",
            "conversation_id": str(first.conversation_id),
            "text": "Dono orders ka paisa include kiya hai na? Aur payment ho gaya kya?",
            "received_at": payload.received_at.isoformat(),
        }
        response = await http.post("/messages", json=followup)
        replay = await http.post("/messages", json=followup)
        assert response.status_code == 200 and replay.json() == response.json()
        reply = response.json()["reply"]
        assert "176" in reply and "T795007" in reply and "T206956" in reply
        assert "sandbox" in reply and "ho chuka" in reply
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(PaymentIntent)) == 1
        assert await session.scalar(select(func.count()).select_from(Conversation)) == 1
        assert await session.scalar(select(func.count()).select_from(Message)) == 4
        conversation = await session.get(Conversation, first.conversation_id)
        assert conversation.status == "OPEN"
        assert conversation.context["agent"]["dispute_ids"] == before_context


async def test_new_dispute_in_same_thread_preserves_daily_guard(agent_setup):
    factory, turn, client = agent_setup
    _, first, _, _ = await turn("R027", "20 ko surge nahi mila", extracted(dates=("20",)))
    assert await process_one(factory, client)
    reply, second, _, _ = await turn(
        "R027",
        "21 ko penalty do baar kata",
        extracted("PENALTY", dates=("21",)),
    )
    assert second.conversation_id == first.conversation_id
    assert "10" in reply and "approval" in reply
    async with factory() as session:
        intents = list(await session.scalars(select(PaymentIntent)))
        assert len(intents) == 1 and intents[0].amount == 15
        queues = list(await session.scalars(select(OpsQueue)))
        assert len(queues) == 1 and queues[0].amount == 10
        assert await session.scalar(select(func.count()).select_from(Dispute)) == 2
        assert (await session.get(Conversation, first.conversation_id)).status != "RESOLVED"


async def test_no_shortfall_explanation_keeps_conversation_active(agent_setup):
    factory, turn, _ = agent_setup
    _, first, _, _ = await turn("R008", "T252921 surge missing", extracted(ids=("T252921",)))
    async with factory() as session:
        assert (await session.get(Conversation, first.conversation_id)).status == "OPEN"
        assert await session.scalar(select(func.count()).select_from(PaymentIntent)) == 0


async def test_reconciliation_never_reopens_explicitly_closed_thread(agent_setup):
    factory, turn, client = agent_setup
    _, first, _, _ = await turn("R007", "T840677 surge missing", extracted(ids=("T840677",)))
    assert await process_one(factory, client)
    async with factory() as session, session.begin():
        intent = await session.scalar(select(PaymentIntent))
        identifier = intent.id
        # Represents an already authorized Ops closure; the public route is covered separately.
        (await session.get(Conversation, first.conversation_id)).status = "RESOLVED"
    assert await reconcile_intent(factory, client, identifier) == "SUCCEEDED"
    async with factory() as session:
        assert (await session.get(Conversation, first.conversation_id)).status == "RESOLVED"
