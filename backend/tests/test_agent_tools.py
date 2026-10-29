from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_payments_database import provider as provider

from app.agent.state import Extraction
from app.agent.tools import AgentTools
from app.models import Message, OpsQueue, PaymentIntent
from app.schemas.messages import IncomingMessage
from app.services import message_service
from app.services.financial.types import ClaimRequest

pytestmark = pytest.mark.database
STAMP = datetime.fromisoformat("2026-09-22T09:05:00+05:30")


@pytest_asyncio.fixture
async def tool_setup(connection, seeded, provider):
    factory = async_sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        autoflush=False,
    )
    client, _ = provider
    incoming = IncomingMessage(
        message_id="tool." + uuid4().hex, rider_id="R003", text="T926334 surge", received_at=STAMP
    )
    claimed = await message_service.claim(factory, incoming)
    return AgentTools(factory, claimed, client), factory, claimed


async def test_tools_profile_history_ownership_and_reconciliation(tool_setup):
    tools, _, _ = tool_setup
    assert (await tools.get_rider_profile())["rider_id"] == "R003"
    request = ClaimRequest(rider_id="R003", received_at=STAMP, trip_ids=("T926334",))
    assert (await tools.get_rider_trips(request))[0]["trip_id"] == "T926334"
    assert len(await tools.get_payout_history(request)) == 1
    result, coverage = await tools.reconcile_dispute(request)
    assert coverage and result.outstanding == 25 and result.status == "VERIFIED"
    foreign = ClaimRequest(rider_id="R003", received_at=STAMP, trip_ids=("T252921",))
    with pytest.raises(ValueError, match="trusted rider"):
        await tools.get_rider_trips(foreign)
    with pytest.raises(ValueError, match="identity"):
        await tools.get_payout_history(request.model_copy(update={"rider_id": "R008"}))


async def test_tools_context_payment_intent_and_idempotency(tool_setup):
    tools, factory, claimed = tool_setup
    extraction = Extraction(
        intent="complaint", language="hinglish", claims=[{"kind": "SURGE", "trip_ids": ["T926334"]}]
    )
    await tools.checkpoint(extraction)
    loaded = await tools.load_context()
    assert loaded["saved"]["claims"][0]["trip_ids"] == ["T926334"]
    assert loaded["context"]["extraction"]["claims"][0]["date_tokens"] == []
    request = ClaimRequest(rider_id="R003", received_at=STAMP, trip_ids=("T926334",))
    result, coverage = await tools.reconcile_dispute(request)
    assert await tools.check_payment_eligibility(request, result)
    dispute = await tools.ensure_dispute(request, result)
    assert await tools.ensure_dispute(request, result) == dispute
    authorized = await tools.create_payment_intent(dispute, request, coverage=coverage)
    assert authorized.status == "AUTHORIZED"
    again = await tools.create_payment_intent(dispute, request, coverage=coverage)
    assert again.status == "EXISTING" and again.intent_id == authorized.intent_id
    async with factory() as session:
        intent = await session.get(PaymentIntent, authorized.intent_id)
        assert intent.amount == 25 and intent.status == "PENDING"
        assert (await session.get(Message, claimed.message_id)).processing_status == "PROCESSING"


async def test_tools_escalation_is_persistent_and_deduplicated(tool_setup):
    tools, factory, _ = tool_setup
    request = ClaimRequest(rider_id="R003", received_at=STAMP, trip_ids=("T926334",))
    result, _ = await tools.reconcile_dispute(request)
    identifier = await tools.ensure_dispute(request, result)
    first = await tools.create_ops_escalation(identifier, "Rider disputes source records")
    again = await tools.create_ops_escalation(identifier, "Rider disputes source records")
    assert first.queue_id == again.queue_id
    async with factory() as session:
        queue = await session.get(OpsQueue, first.queue_id)
        assert queue.type == "escalation" and queue.amount is None
        assert not list(await session.scalars(select(PaymentIntent)))
