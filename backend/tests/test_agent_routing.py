"""Regression proofs for the actual premature-review trace, without live payments."""

from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from test_agent_graph import agent_setup as agent_setup
from test_agent_graph import extracted
from test_agent_webhook import request
from test_payments_database import provider as provider

from app.agent import llm
from app.agent.state import Extraction
from app.agent.tools import investigation
from app.core.database import get_session_factory
from app.main import create_app
from app.models import AgentTrace, Conversation, OpsQueue, PaymentIntent
from app.repositories import financial
from app.services import message_service
from app.services.conversation_service import summary

pytestmark = pytest.mark.database


async def test_actual_october_timestamp_is_not_rewritten(agent_setup):
    factory, turn, _ = agent_setup
    reply, claimed, _, _ = await turn(
        "R003",
        "T926334 ka surge nahi mila 20 tarikh wala",
        extracted(ids=("T926334",), dates=("20",)),
        stamp=datetime.fromisoformat("2026-10-29T07:23:00.389+00:00"),
    )
    assert "eligibility window" in reply
    async with factory() as session:
        traces = list(
            await session.scalars(
                select(AgentTrace).where(AgentTrace.conversation_id == claimed.conversation_id)
            )
        )
        assert "get_payout_history" in {t.name for t in traces}
        assert "evidence_conflict" not in {t.name for t in traces}
        reconciliation = next(t.output for t in traces if t.name == "reconcile_dispute")
        assert reconciliation["status"] == "INELIGIBLE"
        authorization = next(t.output for t in traces if t.name == "payment_authorization")
        assert authorization["status"] == "ESCALATED"
        queue = await session.scalar(select(OpsQueue))
        assert queue.type == "escalation" and queue.amount is None
        conversation = await session.get(Conversation, claimed.conversation_id)
        assert summary((conversation, "", ""))["status"] == "ESCALATED"
        assert not list(await session.scalars(select(PaymentIntent)))


@pytest.mark.parametrize("intent", ["other", "status"])
async def test_model_cannot_skip_explicit_trip_complaint(agent_setup, intent):
    factory, turn, _ = agent_setup
    reply, _, _, _ = await turn(
        "R003", "T926334 ka surge nahi mila", {"intent": intent, "language": "hinglish"}
    )
    assert "25" in reply
    async with factory() as session:
        assert (await session.scalar(select(PaymentIntent))).status == "PENDING"
        assert not list(await session.scalars(select(OpsQueue)))


async def test_unsupported_claim_does_not_create_financial_approval(agent_setup):
    factory, turn, _ = agent_setup
    reply, _, _, _ = await turn(
        "R003", "Please change my vehicle insurance", {"intent": "other", "language": "en"}
    )
    assert "trip payouts" in reply
    async with factory() as session:
        assert not list(await session.scalars(select(PaymentIntent)))
        assert not list(await session.scalars(select(OpsQueue)))


async def test_unknown_trip_requests_details_before_escalating(agent_setup):
    factory, turn, _ = agent_setup
    reply, _, _, _ = await turn(
        "R003", "T999999999 surge missing", extracted(ids=("T999999999",), language="en")
    )
    assert "T999999999" in reply and "could not find" in reply
    assert "no payment has been requested" in reply
    async with factory() as session:
        assert not list(await session.scalars(select(PaymentIntent)))
        assert not list(await session.scalars(select(OpsQueue)))


async def test_model_routing_guard_preserves_explicit_date_conflict(agent_setup):
    factory, turn, _ = agent_setup
    reply, _, _, _ = await turn(
        "R003", "T926334 surge missing 19 sept", {"intent": "other", "language": "en"}
    )
    assert "date" in reply.lower()
    async with factory() as session:
        assert not list(await session.scalars(select(PaymentIntent)))
        assert not list(await session.scalars(select(OpsQueue)))


@pytest.mark.parametrize("failure", ["payout_value_error", "provider_unavailable"])
async def test_tool_failure_is_retryable_not_financial_approval(agent_setup, monkeypatch, failure):
    from app.integrations.payswift import ProviderUnavailable

    factory, _, client = agent_setup
    monkeypatch.setattr(
        llm,
        "extract",
        AsyncMock(
            return_value=Extraction.model_validate(extracted(ids=("T926334",), dates=("20",)))
        ),
    )
    monkeypatch.setattr(investigation, "get_payswift_client", lambda: client)
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    with monkeypatch.context() as patch:
        if failure == "payout_value_error":
            patch.setattr(
                financial, "payouts_for_scope", AsyncMock(side_effect=ValueError("bad tool data"))
            )
            tool = "get_payout_history"
        else:
            patch.setattr(client, "ledger", AsyncMock(side_effect=ProviderUnavailable("offline")))
            tool = "reconcile_dispute"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            response = await http.post("/messages", json=request(text="T926334 surge missing 20"))
        assert response.status_code == 503
    async with factory() as session:
        trace = await session.scalar(
            select(AgentTrace).where(AgentTrace.name == "agent_tool_failed")
        )
        assert trace.type == "error" and trace.output["tool"] == tool
        assert trace.output["retryable"] is True
        assert not list(await session.scalars(select(OpsQueue)))
        assert not list(await session.scalars(select(PaymentIntent)))
    # The durable worker recovers the saved extraction after the dependency recovers.
    assert await message_service.resume_one(factory)
    async with factory() as session:
        intent = await session.scalar(select(PaymentIntent))
        assert intent.status == "PENDING" and intent.amount == 25
        assert not list(await session.scalars(select(OpsQueue)))
