from datetime import datetime

import pytest
from sqlalchemy import select
from test_agent_graph import agent_setup as agent_setup
from test_agent_graph import extracted
from test_payments_database import provider as provider

from app.agent.nodes import expand_investigation_scope, scope_requests
from app.agent.state import Extraction
from app.models import PaymentIntent


def test_scope_expands_count_evidence_without_granting_entitlement():
    text = "kal ka payout kam aaya hai. 12 se zyada order kiye the maine"
    original = Extraction.model_validate(extracted("PAYOUT", dates=("kal",)))
    state = {
        "text": text,
        "history": [],
        "rider_id": "R005",
        "received_at": datetime.fromisoformat("2026-09-22T09:20:00+05:30"),
    }
    expanded = expand_investigation_scope(original, state)
    assert [claim.kind for claim in expanded.claims] == ["PAYOUT", "INCENTIVE"]
    assert len(expand_investigation_scope(expanded, state).claims) == 2
    requests = scope_requests(expanded, state)
    assert requests[1].incentive_dates[0].isoformat() == "2026-09-21"
    assert len(original.claims) == 1


@pytest.mark.parametrize("text", ["T123 ka payout kam, 12 orders", "kal ka payout kam"])
def test_trip_scope_or_no_count_does_not_expand(text):
    original = Extraction.model_validate(
        extracted("PAYOUT", ids=("T123",) if "T123" in text else (), dates=("kal",))
    )
    assert expand_investigation_scope(original, {"text": text}) == original


def test_missing_day_is_not_guessed():
    original = Extraction.model_validate(extracted("PAYOUT"))
    assert expand_investigation_scope(original, {"text": "12 orders payout kam"}) == original


@pytest.mark.database
@pytest.mark.parametrize(
    "rider,text,day,amount",
    [
        ("R005", "kal ka payout kam aaya hai. 12 se zyada order kiye the maine", "kal", 150),
        ("R025", "19 tarikh ka payout kam hai, 12 orders kiye", "19", 0),
        ("R009", "17 ko payout kam hai, 12 orders kiye", "17", 0),
    ],
)
async def test_generic_earnings_checks_real_bonus_evidence(agent_setup, rider, text, day, amount):
    factory, turn, _ = agent_setup
    await turn(
        rider,
        text,
        extracted("PAYOUT", dates=(day,)),
        stamp=datetime.fromisoformat("2026-09-22T09:20:00+05:30"),
    )
    async with factory() as session:
        intents = list(await session.scalars(select(PaymentIntent)))
        assert sum(intent.amount for intent in intents) == amount
        assert len(intents) == (1 if amount else 0)
