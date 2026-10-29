"""Education remains separate from financial authorization and private account facts."""

import pytest
from sqlalchemy import select
from test_agent_graph import agent_setup as agent_setup
from test_payments_database import provider as provider

from app.agent.education import educational_reply
from app.agent.state import Extraction
from app.models import OpsQueue, PaymentIntent


def state(topic, language="en", history=None, **extra):
    return {
        "extraction": Extraction(intent="help", language=language, help_topic=topic, **extra),
        "history": history or [],
    }


@pytest.mark.parametrize("language", ["en", "hi", "hinglish"])
def test_fare_example_is_correct_and_is_not_a_personal_payout(language):
    first = educational_reply(state("fare", language))
    second = educational_reply(
        state("fare", language, [{"sender": "AI", "text": first}], simplify=True)
    )
    assert first != second
    assert "₹25" in first and "₹6" in first
    assert "₹43" in second and "₹65" in second


@pytest.mark.parametrize(
    "topic", ["surge", "incentive", "penalty", "window", "approval", "payment"]
)
@pytest.mark.parametrize("language", ["en", "hi", "hinglish"])
def test_policy_followup_changes_explanation_without_changing_policy(topic, language):
    first = educational_reply(state(topic, language))
    second = educational_reply(state(topic, language, [{"sender": "AI", "text": first}]))
    assert first and second and first != second


def test_general_factual_answer_and_repeated_answer_guard():
    answer = "UPI is a way to send money between bank accounts using a payment app."
    assert educational_reply(state("general", help_answer=answer)) == answer
    repeated = educational_reply(
        state(
            "general",
            history=[{"sender": "AI", "text": answer}, {"sender": "RIDER", "text": "Explain more"}],
            help_answer=answer,
        )
    )
    assert repeated != answer
    assert "Which part" in repeated
    unsafe = educational_reply(state("general", help_answer="Your ₹999 payment is approved."))
    assert "₹999" not in unsafe and "approved" not in unsafe


@pytest.mark.database
async def test_help_and_simpler_followup_do_not_create_claims(agent_setup):
    factory, turn, _ = agent_setup
    first, _, _, _ = await turn(
        "R003",
        "How is my trip fare calculated?",
        {"intent": "help", "language": "en", "help_topic": "fare"},
    )
    second, _, _, _ = await turn(
        "R003",
        "Please explain more simply",
        {"intent": "help", "language": "en", "help_topic": "fare", "simplify": True},
    )
    assert "₹25" in first and "₹65" in second and first != second
    async with factory() as session:
        assert not list(await session.scalars(select(PaymentIntent)))
        assert not list(await session.scalars(select(OpsQueue)))


@pytest.mark.database
async def test_misclassified_actual_fare_complaint_still_investigates(agent_setup):
    factory, turn, _ = agent_setup
    reply, _, _, _ = await turn(
        "R003", "T926334 surge missing", {"intent": "help", "language": "en", "help_topic": "surge"}
    )
    assert "25" in reply
    async with factory() as session:
        payments = list(await session.scalars(select(PaymentIntent)))
        assert len(payments) == 1 and payments[0].amount == 25


def test_simplify_followup_retains_previous_policy_topic():
    from datetime import datetime

    from app.agent.understanding import repair

    fixed = repair(
        Extraction(intent="help", language="hinglish", simplify=True),
        {
            "text": "samajh nahi aaya",
            "received_at": datetime.fromisoformat("2026-09-23T12:30:00+05:30"),
            "context": {"extraction": {"help_topic": "fare"}},
        },
    )
    assert fixed.help_topic == "fare"


@pytest.mark.parametrize(
    "answer", ["Your payment has completed.", "Aapka payment complete hai.", "आपका भुगतान हो गया है।"]
)
def test_general_education_cannot_assert_personal_payment_success(answer):
    reply = educational_reply(state("general", help_answer=answer))
    assert reply != answer
