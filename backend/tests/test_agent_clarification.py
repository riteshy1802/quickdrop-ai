"""Missing-details responses acknowledge the current turn without inventing outcomes."""

from datetime import datetime

import pytest
from sqlalchemy import func, select
from test_agent_graph import agent_setup as agent_setup
from test_agent_graph import extracted
from test_payments_database import provider as provider

from app.agent.clarification import clarification_reply, lacks_details
from app.agent.state import Extraction
from app.models import Conversation, Dispute, OpsQueue, PaymentIntent


@pytest.mark.parametrize(
    "text",
    [
        "hm voh toh nai hai",
        "are bola na hai hi nai mere pass details",
        "I don't have the details",
        "I do not remember",
        "मेरे पास जानकारी नहीं है",
    ],
)
def test_recognizes_unavailable_details(text):
    assert lacks_details(text)


@pytest.mark.parametrize(
    "draft",
    [
        "Your payment is approved",
        "₹999 bhej diye",
        "Maine case support team ko bhej diya",
        "आपका भुगतान हो गया",
        "I checked your records",
        "You will get your money back",
    ],
)
def test_model_clarification_cannot_invent_financial_or_review_state(draft):
    state = {
        "text": "I have no details",
        "history": [],
        "context": {"pending_clarification": {"missing": ["Trip ID or date"]}},
        "extraction": Extraction(
            intent="followup", language="en", details_unavailable=True, clarification_answer=draft
        ),
    }
    reply = clarification_reply(state)
    assert draft not in reply
    assert "cannot verify" in reply


def test_model_wording_is_used_instead_of_a_fixed_clarification():
    draft = "I hear you. Is there a day you roughly remember?"
    state = {
        "text": "no details",
        "history": [],
        "context": {"pending_clarification": {"missing": ["Trip ID or date"]}},
        "extraction": Extraction(
            intent="followup", language="en", details_unavailable=True, clarification_answer=draft
        ),
    }
    assert clarification_reply(state).startswith(draft)
    state["history"] = [{"sender": "AI", "text": draft + " Without details I cannot proceed."}]
    assert not clarification_reply(state).startswith(draft)


@pytest.mark.database
async def test_refusal_acknowledges_then_supplied_date_resumes_real_investigation(agent_setup):
    factory, turn, _ = agent_setup
    first, claimed, model, _ = await turn(
        "R014",
        "cancellation ke liye do baar charge hua",
        extracted("PENALTY"),
    )
    model.assert_awaited_once()
    second, _, _, _ = await turn(
        "R014",
        "hm voh toh nai hai",
        {"intent": "complaint", "language": "en"},
    )
    third, _, _, _ = await turn(
        "R014",
        "are bola na hai hi nai mere pass details",
        extracted("PENALTY"),
    )
    assert len({first, second, third}) == 3
    assert "aapke paas abhi details nahi hain" in second
    assert "aapne bataya ki details nahi hain" in third
    assert "nahi kar sakta" in second and "nahi kar sakta" in third
    async with factory() as session:
        for model in (Dispute, OpsQueue, PaymentIntent):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
        conversation = await session.get(Conversation, claimed.conversation_id)
        assert conversation.status == "AWAITING_INFORMATION"
        assert conversation.context["agent"]["pending_clarification"]
    final, resumed, _, _ = await turn(
        "R014",
        "18 ko tha",
        extracted("PENALTY", dates=("18",)),
        stamp=datetime.fromisoformat("2026-09-23T10:00:00+05:30"),
    )
    assert resumed.conversation_id == claimed.conversation_id
    assert "10" in final
    async with factory() as session:
        intents = list(await session.scalars(select(PaymentIntent)))
        assert len(intents) == 1 and intents[0].amount == 10
        assert (
            not (await session.get(Conversation, claimed.conversation_id))
            .context["agent"]
            .get("pending_clarification")
        )


@pytest.mark.database
async def test_safe_model_followup_text_is_rendered_without_extra_model_call(agent_setup):
    _, turn, _ = agent_setup
    await turn("R003", "payout nahi mila", extracted("PAYOUT"))
    draft = "Samajh gaya. Koi lagbhag din ya purane order ka message yaad hai?"
    reply, _, model, _ = await turn(
        "R003",
        "details nahi mil rahi",
        {
            "intent": "help",
            "language": "hinglish",
            "details_unavailable": True,
            "clarification_answer": draft,
        },
    )
    assert reply.startswith(draft)
    assert "nahi kar sakta" in reply
    model.assert_awaited_once()


@pytest.mark.database
async def test_details_supplied_for_a_fully_paid_trip_clear_awaiting_information(agent_setup):
    factory, turn, _ = agent_setup
    await turn("R008", "surge missing", extracted())
    _, claimed, _, _ = await turn("R008", "T252921", extracted(ids=("T252921",)))
    async with factory() as session:
        conversation = await session.get(Conversation, claimed.conversation_id)
        assert conversation.status == "OPEN"
        assert "pending_clarification" not in conversation.context["agent"]
        assert await session.scalar(select(func.count()).select_from(PaymentIntent)) == 0
