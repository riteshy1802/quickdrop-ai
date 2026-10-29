"""Replay all 24 assignment scenarios with extraction labels and a controlled provider."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from test_agent_graph import agent_setup as agent_setup
from test_payments_database import provider as provider

from app.agent.graph import run_agent
from app.agent.state import Extraction
from app.core.config import BACKEND_DIR
from app.models import OpsQueue, PaymentIntent
from app.schemas.messages import IncomingMessage
from app.services import message_service
from app.services.payment_worker import process_one

pytestmark = pytest.mark.database
SCENARIOS = json.loads((BACKEND_DIR.parent / "data/conversations.json").read_text())
LABELS = json.loads((Path(__file__).parent / "fixtures/agent_extractions.json").read_text())


@pytest.mark.parametrize(
    "index", range(24), ids=[s["scenario"] + f"-{i + 1}" for i, s in enumerate(SCENARIOS)]
)
async def test_assignment_scenario(agent_setup, index):
    factory, _, client = agent_setup
    scenario = SCENARIOS[index]
    rider_turns = [turn for turn in scenario["turns"] if turn["from"] == "rider"]
    replies = []
    for position, turn in enumerate(rider_turns):
        request = IncomingMessage(
            message_id=turn["message_id"],
            rider_id=scenario["rider_id"],
            text=turn["text"],
            received_at=turn["received_at"],
        )
        claimed = await message_service.claim(factory, request)
        if isinstance(claimed, str):
            replies.append(claimed)
            continue
        label = LABELS[index][position]
        if isinstance(label, str):
            extraction = Extraction(intent=label, language="hinglish")
        else:
            claims = [label]
            if index == 1 and position == 0:
                claims.append({"kind": "PENALTY", "date_tokens": ["21"]})
            extraction = Extraction(
                intent="complaint",
                language="en" if index == 17 else "hinglish",
                claims=claims,
                records_disputed=index == 2 and position == 1,
            )
        reply = await run_agent(
            factory, claimed, client=client, extractor=AsyncMock(return_value=extraction)
        )
        replies.append(await message_service.complete(factory, claimed, reply))
        # Simulate one existing durable worker tick; this never calls a real provider.
        await process_one(factory, client)
    async with factory() as session:
        intents = list(await session.scalars(select(PaymentIntent)))
        approvals = list(await session.scalars(select(OpsQueue).where(OpsQueue.type == "approval")))
        escalations = list(
            await session.scalars(select(OpsQueue).where(OpsQueue.type == "escalation"))
        )
    actual = {
        "payout": sum(int(i.amount) for i in intents if i.status == "SUCCEEDED"),
        "approval": sum(int(q.amount) for q in approvals) if approvals else None,
    }
    expected = scenario["expected"]
    if "one_of" in expected:
        assert actual in expected["one_of"]
    else:
        assert actual == {"payout": expected["payout"], "approval": expected["approval"]}
    if expected["escalation"] == "no":
        assert not escalations
    for mention in expected.get("reply_mentions", []):
        assert mention in " ".join(replies)
