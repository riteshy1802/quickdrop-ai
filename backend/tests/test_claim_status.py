"""Same-claim confirmation and duplicate handling without real transfers."""

import httpx
import pytest
from sqlalchemy import func, select
from test_agent_graph import agent_setup as agent_setup
from test_agent_graph import extracted
from test_payments_database import provider as provider

from app.core.database import get_db_session, get_session_factory
from app.main import create_app
from app.models import PaymentIntent
from app.services.payment_worker import process_one

pytestmark = pytest.mark.database


async def test_paid_repeat_and_confirmation_followup_have_distinct_answers_and_details(agent_setup):
    factory, turn, client = agent_setup
    _, first, _, _ = await turn("R007", "T840677 surge missing", extracted(ids=("T840677",)))
    assert await process_one(factory, client)
    duplicate, repeated, _, _ = await turn(
        "R007", "T840677 ka surge missing hai bhai", extracted(ids=("T840677",))
    )
    assert repeated.conversation_id != first.conversation_id
    assert "pehle hi ho chuka" in duplicate and "dobara nahi" in duplicate
    assert "34" in duplicate and "T840677" in duplicate and "sandbox" in duplicate
    clarified, _, _, _ = await turn(
        "R007",
        "matlab payment ho chuka hai?",
        extracted(ids=("T840677",), intent="status"),
    )
    assert clarified != duplicate and clarified.startswith("Haan,")
    assert "bank account mein real paise transfer nahi" in clarified
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(PaymentIntent)) == 1
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory

    async def isolated_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = isolated_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        await http.post("/ui/demo/rider", json={"rider_id": "R007"})
        base = f"/ui/conversations/{repeated.conversation_id}"
        disputes = await http.get(base + "/disputes", params={"rider_id": "R007"})
        payouts = await http.get(base + "/payouts", params={"rider_id": "R007"})
        assert disputes.status_code == payouts.status_code == 200
        assert disputes.json()["total"] == payouts.json()["total"] == 1
        assert payouts.json()["items"][0]["status"] == "SUCCEEDED"


async def test_unrelated_trip_status_does_not_pick_latest_paid_claim(agent_setup):
    factory, turn, client = agent_setup
    await turn("R007", "T840677 surge missing", extracted(ids=("T840677",)))
    assert await process_one(factory, client)
    reply, _, _, _ = await turn(
        "R007",
        "T999999999 payment status?",
        extracted(ids=("T999999999",), intent="status", language="en"),
    )
    assert "₹34" not in reply and "completed" not in reply


async def test_provider_unavailable_preserves_previous_confirmation_without_claiming_fresh_check(
    agent_setup, provider
):
    _, turn, client = agent_setup
    factory = agent_setup[0]
    await turn("R007", "T840677 surge missing", extracted(ids=("T840677",)))
    assert await process_one(factory, client)
    provider[1].bad_ledger = True
    reply, _, _, _ = await turn(
        "R007",
        "T840677 payment status?",
        extracted(ids=("T840677",), intent="status", language="en"),
    )
    assert "previously confirmed" in reply and "cannot verify" in reply
    assert "queued" not in reply


async def test_duplicate_approval_and_eta_answer_different_questions_without_new_money(agent_setup):
    from app.models import OpsQueue

    factory, turn, _ = agent_setup
    await turn(
        "R016", "19 sept ke orders ka paisa nahi aaya", extracted("PAYOUT", dates=("19 sept",))
    )
    # Deliberately wrong model classification must not reopen this same claim.
    duplicate, _, _, _ = await turn(
        "R016",
        "nahi me keh raha hu aur ek adjustment request daalo",
        extracted("PAYOUT", dates=("19 sept",)),
    )
    timing, _, _, _ = await turn(
        "R016",
        "acha, kab tak hojayega?",
        {"intent": "other", "language": "en"},
    )
    assert "doosri adjustment request nahi" in duplicate
    assert "approval" in duplicate and "initiate nahi" in duplicate
    assert "exact waqt" in timing and "Pehle approval" in timing
    assert timing != duplicate
    async with factory() as session:
        queues = list(await session.scalars(select(OpsQueue)))
        assert len(queues) == 1 and queues[0].amount == 425
        assert not list(await session.scalars(select(PaymentIntent)))


async def test_request_another_paid_adjustment_checks_provider_and_refuses_duplicate(agent_setup):
    factory, turn, client = agent_setup
    await turn("R007", "T840677 surge missing", extracted(ids=("T840677",)))
    assert await process_one(factory, client)
    reply, _, _, _ = await turn(
        "R007",
        "T840677 ke liye ek aur adjustment request daalo bhai",
        extracted(ids=("T840677",), intent="status"),
    )
    assert "pehle hi ho chuka" in reply and "same payment dobara nahi" in reply
    assert "₹34" in reply and "sandbox" in reply
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(PaymentIntent)) == 1


async def test_unscoped_duplicate_in_new_thread_does_not_guess_latest_payment(agent_setup):
    factory, turn, client = agent_setup
    await turn("R007", "T840677 surge missing", extracted(ids=("T840677",)))
    assert await process_one(factory, client)
    reply, _, _, _ = await turn(
        "R007", "ek aur adjustment request daalo bhai", {"intent": "other", "language": "en"}
    )
    assert "Kis trip ya date" in reply and "₹34" not in reply
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(PaymentIntent)) == 1
