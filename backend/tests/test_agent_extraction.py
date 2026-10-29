from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.agent import llm
from app.agent.dates import grounded, resolve_date
from app.agent.state import Extraction

STAMP = datetime.fromisoformat("2026-09-23T00:15:00+05:30")


@pytest.mark.parametrize(
    "token,expected",
    [
        ("kal", "2026-09-22"),
        ("कल", "2026-09-22"),
        ("20", "2026-09-20"),
        ("19 sept", "2026-09-19"),
        ("Sep 19", "2026-09-19"),
        ("19th", "2026-09-19"),
        ("२०", "2026-09-20"),
        ("2026-09-13", "2026-09-13"),
    ],
)
def test_dates_use_vendor_ist_timestamp(token, expected):
    assert resolve_date(token, STAMP).isoformat() == expected


def test_date_grounding_and_previous_month():
    assert not grounded("20", "200 rupees")
    assert grounded("20", "20 wala")
    assert (
        resolve_date("31", datetime.fromisoformat("2026-09-02T00:00:00+05:30")).isoformat()
        == "2026-08-31"
    )


async def test_structured_extraction(monkeypatch):
    model = AsyncMock()
    model.ainvoke.return_value = {
        "intent": "complaint",
        "language": "hinglish",
        "claims": [{"kind": "SURGE", "trip_ids": ["T1"]}],
    }
    monkeypatch.setattr(llm, "get_extractor", lambda: model)
    result = await llm.extract(text="T1 surge", received_at=STAMP, history=[], context={})
    assert isinstance(result, Extraction) and result.claims[0].trip_ids == ["T1"]
    assert model.ainvoke.await_count == 1


async def test_malformed_output_has_sanitized_error(monkeypatch):
    model = AsyncMock()
    model.ainvoke.return_value = {"api_key": "private", "amount": 999}
    monkeypatch.setattr(llm, "get_extractor", lambda: model)
    with pytest.raises(llm.ExtractionUnavailable) as error:
        await llm.extract(text="hello", received_at=STAMP, history=[], context={})
    assert "private" not in str(error.value)


def test_date_entity_fields_are_not_mistaken_for_credentials():
    from app.services.trace_service import safe_json

    payload = safe_json({"date_tokens": ["kal"], "access_token": "private", "token": "private"})
    assert payload["date_tokens"] == ["kal"]
    assert payload["access_token"] == payload["token"] == "[REDACTED]"


def test_explicit_future_month_is_not_silently_rewritten():
    assert resolve_date("Sep 30", STAMP).isoformat() == "2026-09-30"


def test_groq_initialization_uses_bounded_settings(monkeypatch):
    from unittest.mock import Mock

    from app.core.config import Settings

    settings = Settings(_env_file=None, groq_api_key="synthetic-test-key")
    model = Mock()
    constructor = Mock(return_value=model)
    monkeypatch.setattr(llm, "ChatGroq", constructor)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    llm.get_extractor.cache_clear()
    try:
        llm.get_extractor()
        kwargs = constructor.call_args.kwargs
        assert kwargs["model"] == "openai/gpt-oss-20b"
        assert kwargs["max_retries"] == 0 and kwargs["temperature"] == 0
        model.with_structured_output.assert_called_once_with(Extraction, method="function_calling")
    finally:
        llm.get_extractor.cache_clear()


def test_relative_followup_keeps_original_vendor_day():
    from app.agent.nodes import scope_requests

    state = {
        "rider_id": "R003",
        "text": "check again",
        "received_at": STAMP,
        "history": [
            {
                "sender": "RIDER",
                "text": "kal surge missing",
                "received_at": "2026-09-22T10:00:00+05:30",
            }
        ],
    }
    extraction = Extraction(
        intent="complaint", language="en", claims=[{"kind": "SURGE", "date_tokens": ["kal"]}]
    )
    assert scope_requests(extraction, state)[0].trip_dates[0].isoformat() == "2026-09-21"
