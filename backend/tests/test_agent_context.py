"""Regressions for malformed context and concise, evidence-based rider replies."""

from datetime import datetime

import pytest
from sqlalchemy import select
from test_agent_graph import agent_setup as agent_setup
from test_agent_graph import extracted
from test_payments_database import provider as provider

from app.agent.state import Extraction
from app.agent.understanding import repair, response_language
from app.models import OpsQueue, PaymentIntent


@pytest.mark.database
async def test_invalid_context_then_new_date_claim(agent_setup):
    factory, turn, _ = agent_setup
    reply, _, _, _ = await turn(
        "R016",
        "2999 sept ke 100000 orders ka paisa hi nahi aaya!! jaldi karo",
        extracted("PAYOUT", dates=("2999 sept",)),
    )
    assert "2999 sept" in reply and "valid" in reply
    # Simulate the model carrying the rejected date and misdetecting the language.
    reply, _, _, _ = await turn(
        "R016",
        "T2266262",
        extracted("PAYOUT", ids=("T2266262",), dates=("2999 sept",), language="en"),
    )
    assert "T2266262" in reply and "2999" not in reply
    assert "nahi mila" in reply and "trip ID ya date" not in reply
    reply, _, _, _ = await turn(
        "R016",
        "Meri trip id : T2266262 aur tareek 23 sept",
        extracted("PAYOUT", ids=("T2266262",), dates=("2999 sept", "23 sept"), correction=True),
    )
    assert "T2266262" in reply and "2999" not in reply
    assert "trip ID ya date" not in reply
    async with factory() as session:
        assert not list(await session.scalars(select(PaymentIntent)))
        assert not list(await session.scalars(select(OpsQueue)))

    # The model incorrectly returns both an obsolete claim and the new dated issue.
    label = extracted("PAYOUT", dates=("19 sept",))
    label["claims"].insert(
        0, {"kind": "PENALTY", "trip_ids": ["T2266262"], "date_tokens": ["23 sept"]}
    )
    reply, _, _, _ = await turn(
        "R016", "19 sept ke 5 orders ka paisa hi nahi aaya!! jaldi karo", label
    )
    for expected in (
        "19 September",
        "₹599",
        "₹174",
        "₹425",
        "automatic payment limit",
        "approval",
        "initiate nahi",
    ):
        assert expected in reply
    assert "T2266262" not in reply and "trip ID ya date" not in reply
    assert "T158281" not in reply and len(reply) < 550
    async with factory() as session:
        assert not list(await session.scalars(select(PaymentIntent)))
        approvals = list(await session.scalars(select(OpsQueue)))
        assert len(approvals) == 1 and approvals[0].type == "approval"
        assert approvals[0].amount == 425


def state(text, previous=None):
    return {
        "text": text,
        "received_at": datetime.fromisoformat("2026-09-23T09:05:00+05:30"),
        "context": {"extraction": previous or {}},
    }


def test_bare_id_repairs_model_omission_without_inventing_claim_kind():
    previous = extracted("SURGE")
    fixed = repair(Extraction(intent="other", language="en"), state("T926334", previous))
    assert fixed.intent == "followup"
    assert fixed.claims[0].trip_ids == ["T926334"]
    assert fixed.claims[0].kind == "SURGE"
    unknown = repair(Extraction(intent="other", language="en"), state("T926334"))
    assert not unknown.claims


def test_correction_replaces_old_valid_date_and_preserves_same_message_claims():
    fixed = repair(
        Extraction.model_validate(
            extracted("PAYOUT", dates=("19 sept", "20 sept"), correction=True)
        ),
        state("Nahi, 20 sept"),
    )
    assert fixed.claims[0].date_tokens == ["20 sept"]
    label = extracted("SURGE", dates=("20",))
    label["claims"].append({"kind": "PENALTY", "date_tokens": ["21"]})
    fixed = repair(Extraction.model_validate(label), state("20 ko surge aur 21 ko penalty"))
    assert len(fixed.claims) == 2


@pytest.mark.parametrize("language", ["hinglish", "hi"])
def test_identifier_only_inherits_language_but_english_prose_switches(language):
    context = {"language": language}
    assert response_language("T2266262", "en", context) == language
    assert response_language("23 sept", "en", context) == language
    assert response_language("Please check this trip", "en", context) == "en"


@pytest.mark.database
async def test_date_only_payment_complaint_cannot_be_skipped_by_model(agent_setup):
    factory, turn, _ = agent_setup
    reply, _, _, _ = await turn(
        "R016", "19 sept ke orders ka paisa nahi aaya", {"intent": "other", "language": "en"}
    )
    assert "₹425" in reply and "approval" in reply
    assert "trip ID ya date" not in reply
    async with factory() as session:
        assert not list(await session.scalars(select(PaymentIntent)))
        assert len(list(await session.scalars(select(OpsQueue)))) == 1


def test_new_day_scope_drops_old_trip_even_inside_current_claim():
    fixed = repair(
        Extraction.model_validate(extracted("PAYOUT", ids=("T12345678",), dates=("19 sept",))),
        state("19 sept ke 5 orders ka paisa nahi aaya"),
    )
    assert fixed.claims[0].trip_ids == []
    assert fixed.claims[0].date_tokens == ["19 sept"]
    # A short date correction still refers to the previously identified trip.
    corrected = repair(
        Extraction.model_validate(
            extracted("PAYOUT", ids=("T12345678",), dates=("23 sept",), correction=True)
        ),
        state("23 sept"),
    )
    assert corrected.claims[0].trip_ids == ["T12345678"]
