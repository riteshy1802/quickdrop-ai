import pytest

from app.agent.nodes import language_hint
from app.agent.replies import status_reply


@pytest.mark.parametrize(
    "status", ["NEEDS_REVIEW", "UNKNOWN", "PENDING", "PROCESSING", "FAILED", "AWAITING_APPROVAL"]
)
@pytest.mark.parametrize("language", ["en", "hinglish", "hi"])
def test_rider_payment_states_are_explained_without_raw_codes(status, language):
    reply = status_reply([{"amount": "10", "status": status, "confirmed": False}], language)
    assert "₹10" in reply
    assert status not in reply
    if status in {"NEEDS_REVIEW", "UNKNOWN"}:
        assert {"en": "avoid", "hinglish": "duplicate payment", "hi": "दोबारा"}[
            language
        ] in reply.lower()
    if language == "en":
        assert "nahi" not in reply and "है" not in reply
    if language == "hi":
        assert "आप" in reply and "Payment" not in reply


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Bhai mera penalty do baar kata", "hinglish"),
        ("18 ko penalty galat hai", "hinglish"),
        ("मेरी पेनल्टी दो बार कटी है", "hi"),
        ("Please check my payment status", "en"),
    ],
)
def test_reply_language_matches_current_message(text, expected):
    assert language_hint(text) == expected
