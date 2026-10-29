"""Business clock precedence, durable demo snapshots and real-day payment limits."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from test_agent_graph import agent_setup as agent_setup
from test_agent_graph import extracted
from test_payments_database import provider as provider

from app.agent import llm
from app.agent.dates import resolve_date
from app.agent.graph import run_agent
from app.agent.state import Extraction
from app.agent.tools import investigation
from app.core import clock
from app.core.config import Settings
from app.core.database import get_db_session, get_session_factory
from app.main import create_app
from app.models import AgentTrace, Dispute, Message, OpsQueue, PaymentIntent
from app.schemas.messages import IncomingMessage
from app.services import message_service

REFERENCE = datetime.fromisoformat("2026-09-23T12:30:00+05:30")
OCTOBER = datetime.fromisoformat("2026-10-29T09:00:00+05:30")


@pytest.fixture
def demo_clock(monkeypatch):
    settings = Settings(_env_file=None, app_reference_time=REFERENCE)
    monkeypatch.setattr(clock, "get_settings", lambda: settings)
    return settings


def test_evaluator_timestamp_precedes_demo_clock(demo_clock):
    explicit = datetime.fromisoformat("2026-09-22T09:05:00+05:30")
    assert clock.reference_time(received_at=explicit) == explicit
    assert clock.reference_time(received_at=OCTOBER, interactive_demo=True) == REFERENCE


def test_unset_clock_uses_actual_time(monkeypatch):
    monkeypatch.setattr(clock, "get_settings", lambda: Settings(_env_file=None))
    before = datetime.now(UTC)
    value = clock.reference_time(interactive_demo=True)
    assert before <= value <= datetime.now(UTC)
    assert value.tzinfo == clock.IST


@pytest.mark.parametrize(
    "token,expected", [("kal", "2026-09-22"), ("aaj", "2026-09-23"), ("20 tarikh", "2026-09-20")]
)
def test_relative_dates_use_business_clock(demo_clock, token, expected):
    assert resolve_date(token, clock.reference_time(interactive_demo=True)).isoformat() == expected


def test_production_and_naive_clocks_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", app_reference_time=REFERENCE)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_reference_time="2026-09-23T12:30:00")


@pytest.mark.database
async def test_signed_demo_r003_uses_clock_without_rewriting_old_case(
    agent_setup, demo_clock, monkeypatch
):
    factory, turn, client = agent_setup
    # Preserve the previously observed out-of-window case and its escalation.
    await turn("R003", "T926334 surge missing", extracted(ids=("T926334",)), stamp=OCTOBER)
    async with factory() as session:
        old = await session.scalar(select(Dispute))
        old_id, old_details = old.id, dict(old.details)
    model = AsyncMock(
        return_value=Extraction.model_validate(extracted(ids=("T926334",), dates=("20",)))
    )
    monkeypatch.setattr(llm, "extract", model)
    monkeypatch.setattr(investigation, "get_payswift_client", lambda: client)
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory

    async def isolated_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = isolated_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        assert (await http.post("/ui/demo/rider", json={"rider_id": "R003"})).status_code == 200
        created = await http.post("/ui/riders/R003/conversations")
        cid = created.json()["id"]
        payload = {
            "message_id": uuid4().hex,
            "rider_id": "R003",
            "conversation_id": cid,
            "text": "T926334 ka surge nahi mila, 20 tarikh wala",
            "received_at": OCTOBER.isoformat(),
        }
        response = await http.post("/messages", json=payload)
        assert response.status_code == 200 and "25" in response.json()["reply"]
        assert (await http.post("/messages", json=payload)).json() == response.json()
    assert model.call_args.kwargs["received_at"] == REFERENCE
    async with factory() as session:
        old = await session.get(Dispute, old_id)
        assert old.status == "ESCALATED" and old.details == old_details
        intents = list(await session.scalars(select(PaymentIntent)))
        assert len(intents) == 1 and intents[0].amount == 25
        assert intents[0].payment_type == "AUTO" and intents[0].status == "PENDING"
        assert intents[0].auto_pay_date == datetime.now(UTC).astimezone(clock.IST).date()
        assert (
            datetime.fromisoformat(intents[0].authorization["request"]["reference_time"])
            == REFERENCE
        )
        message = await session.scalar(
            select(Message).where(Message.message_id == payload["message_id"])
        )
        assert (
            message.received_at == OCTOBER and message.created_at.date() == datetime.now(UTC).date()
        )
        trace = await session.scalar(
            select(AgentTrace).where(
                AgentTrace.name == "reconcile_dispute",
                AgentTrace.conversation_id == message.conversation_id,
            )
        )
        assert trace.output["status"] == "VERIFIED"
        assert trace.output["outstanding"] == "25"
    # The worker must use the same durable business clock as initial authorization.
    from app.services.payment_worker import process_one

    assert await process_one(factory, client)
    async with factory() as session:
        intent = await session.scalar(select(PaymentIntent))
        assert intent.status == "SUCCEEDED" and intent.provider_payout_id


@pytest.mark.database
async def test_old_r022_stays_outside_window(agent_setup, demo_clock):
    factory, _, client = agent_setup
    payload = IncomingMessage(
        message_id=uuid4().hex,
        rider_id="R022",
        text="T502951 13 sept surge missing",
        received_at=OCTOBER,
    )
    claimed = await message_service.claim(factory, payload, interactive_demo=True)
    reply = await run_agent(
        factory,
        claimed,
        client=client,
        extractor=AsyncMock(
            return_value=Extraction.model_validate(extracted(ids=("T502951",), dates=("13 sept",)))
        ),
    )
    assert "eligibility window" in reply
    async with factory() as session:
        assert not list(await session.scalars(select(PaymentIntent)))
        assert (await session.scalar(select(OpsQueue))).type == "escalation"


@pytest.mark.database
async def test_changing_demo_clock_cannot_create_second_daily_reservation(agent_setup, demo_clock):
    factory, _, client = agent_setup
    for text, entity in [
        ("20 surge missing", extracted(dates=("20",))),
        ("21 penalty do baar", extracted("PENALTY", dates=("21",))),
    ]:
        payload = IncomingMessage(
            message_id=uuid4().hex, rider_id="R027", text=text, received_at=OCTOBER
        )
        claimed = await message_service.claim(factory, payload, interactive_demo=True)
        reply = await run_agent(
            factory,
            claimed,
            client=client,
            extractor=AsyncMock(return_value=Extraction.model_validate(entity)),
        )
        await message_service.complete(factory, claimed, reply)
        demo_clock.app_reference_time = REFERENCE.replace(day=24)
    async with factory() as session:
        intents = list(await session.scalars(select(PaymentIntent)))
        assert len(intents) == 1 and intents[0].amount == 15
        assert intents[0].auto_pay_date == datetime.now(UTC).astimezone(clock.IST).date()
        queue = await session.scalar(select(OpsQueue).where(OpsQueue.type == "approval"))
        assert queue.amount == 10
