from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.access import require_local_development
from app.core.config import Settings
from app.main import create_app
from app.models import Conversation
from app.schemas.messages import IncomingMessage
from app.services import conversation_service, trace_service


def test_payload_preserves_exact_content_and_requires_timezone():
    message = IncomingMessage(
        message_id="id", rider_id="R003", text=" text ", received_at="2026-09-22T09:05:00Z"
    )
    assert message.text == " text "
    assert message.received_at.utcoffset() is not None


@pytest.mark.parametrize(
    "environment,enabled,host,allowed",
    [
        ("development", False, "127.0.0.1", False),
        ("production", True, "127.0.0.1", False),
        ("development", True, "192.168.1.10", False),
        ("development", True, "127.0.0.1", True),
        ("development", True, "::1", True),
    ],
)
def test_internal_guard(monkeypatch, environment, enabled, host, allowed):
    from app.core import access

    monkeypatch.setattr(
        access,
        "get_settings",
        lambda: Settings(_env_file=None, app_env=environment, enable_local_internal_reads=enabled),
    )
    request = Request({"type": "http", "client": (host, 1234)})
    if allowed:
        require_local_development(request)
    else:
        with pytest.raises(HTTPException) as exc:
            require_local_development(request)
        assert exc.value.status_code == 403


async def test_privileged_endpoints_fail_closed_without_database(monkeypatch):
    from app.core import access

    monkeypatch.setattr(
        access, "get_settings", lambda: Settings(_env_file=None, enable_local_internal_reads=False)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        for path in (
            "/ui/ops/overview",
            "/ui/ops/payouts",
            "/ui/ops/cases",
            "/ui/ops/traces",
            f"/ui/conversations/{uuid4()}?rider_id=R003",
        ):
            assert (await client.get(path)).status_code == (
                401 if path.startswith("/ui/ops/") else 403
            )


def test_safe_trace_json_and_lifecycle_context():
    now = datetime.now(UTC)
    result = trace_service.safe_json(
        {
            "amount": Decimal("1.234567890123456789"),
            "at": now,
            "id": uuid4(),
            "nested": [{"authorization": "secret"}],
            "token": "private-token",
        }
    )
    assert result["amount"] == "1.234567890123456789"
    assert result["nested"] == [{"authorization": "[REDACTED]"}]
    assert result["token"] == "[REDACTED]"
    conversation = Conversation(status="OPEN", handling_mode="AI", context={})
    conversation_service.set_context(conversation, {"trip_ids": ["T1"], "api_key": "secret"})
    assert conversation_service.get_context(conversation)["trip_ids"] == ["T1"]
    assert conversation.context["api_key"] == "[REDACTED]"
    conversation_service.set_lifecycle(conversation, status="RESOLVED", handling_mode="AI")
    with pytest.raises(ValueError, match="cannot be reopened"):
        conversation_service.set_lifecycle(conversation, status="OPEN", handling_mode="AI")


async def test_missing_session_rejects_before_database_initialization():
    from app.core.database import get_session_factory

    def unavailable():
        raise AssertionError("Unauthenticated requests must not initialize PostgreSQL")

    app = create_app()
    app.dependency_overrides[get_session_factory] = unavailable
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in ("/auth/me", "/ui/ops/overview"):
            assert (await client.get(path)).status_code == 401
