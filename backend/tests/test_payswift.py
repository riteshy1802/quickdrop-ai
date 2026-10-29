"""Controlled HTTP provider only. No calls to the running PaySwift sandbox."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from email.utils import format_datetime
from uuid import uuid4

import httpx
import pytest

from app.integrations import payswift
from app.integrations.payswift import PaySwiftClient, ProviderPayout, ProviderUnavailable
from app.services.payment_reconciliation import match_payout
from app.services.payment_worker import backoff


def payout(**changes):
    return {
        "payout_id": "pout_" + uuid4().hex[:12],
        "rider_id": "R003",
        "amount": 25,
        "reference": "quickdrop:test",
        "status": "processed",
        "created_at": datetime.now(UTC).isoformat(),
        **changes,
    }


@pytest.mark.parametrize(
    "status,kind",
    [
        (201, "CONFIRMED"),
        (400, "REJECTED"),
        (409, "AMBIGUOUS"),
        (429, "RATE_LIMITED"),
        (500, "AMBIGUOUS"),
        (503, "AMBIGUOUS"),
        (302, "AMBIGUOUS"),
    ],
)
async def test_provider_statuses_and_exact_request(status, kind):
    calls = []

    async def provider(request):
        calls.append(request)
        return httpx.Response(status, json=payout(), headers={"Retry-After": "10"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider), base_url="http://provider"
    ) as http:
        client = PaySwiftClient(http)
        for _ in range(2):
            result = await client.post(
                rider_id="R003", amount=25, reference="quickdrop:test", idempotency_key="stable-key"
            )
            assert result.kind == kind
            if status == 429:
                assert result.retry_after == 10
    assert all(request.headers["Idempotency-Key"] == "stable-key" for request in calls)
    import json

    assert json.loads(calls[0].content) == {
        "rider_id": "R003",
        "amount": 25,
        "reference": "quickdrop:test",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": 26},
        {"rider_id": "R004"},
        {"reference": "other"},
        {"payout_id": ""},
        {"amount": 25.0},
        {"status": "pending"},
        {"created_at": "2026-09-22T09:00:00"},
    ],
)
async def test_invalid_or_mismatched_201_is_ambiguous(changes):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(201, json=payout(**changes))),
        base_url="http://provider",
    ) as http:
        outcome = await PaySwiftClient(http).post(
            rider_id="R003", amount=25, reference="quickdrop:test", idempotency_key="key"
        )
        assert outcome.kind == "AMBIGUOUS"


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError]
)
async def test_network_errors_never_mean_failed(error):
    async def provider(request):
        raise error("private-provider-detail", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider), base_url="http://provider"
    ) as http:
        client = PaySwiftClient(http)
        assert (
            await client.post(
                rider_id="R003", amount=25, reference="quickdrop:test", idempotency_key="key"
            )
        ).kind == "AMBIGUOUS"
        with pytest.raises(ProviderUnavailable):
            await client.ledger("R003")
        assert not await client.health()


async def test_slow_provider_has_total_budget(monkeypatch):
    monkeypatch.setattr(payswift, "REQUEST_BUDGET_SECONDS", 0.01)

    async def provider(request):
        await asyncio.sleep(1)
        return httpx.Response(201, json=payout())

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider), base_url="http://provider"
    ) as http:
        result = await PaySwiftClient(http).post(
            rider_id="R003", amount=25, reference="quickdrop:test", idempotency_key="key"
        )
        assert result.kind == "AMBIGUOUS"


@pytest.mark.parametrize(
    "body",
    [
        {"data": [], "count": 1},
        {"data": [payout(rider_id="R004")], "count": 1},
        {"data": [{}], "count": 1},
        [],
        {"data": [], "count": "0"},
    ],
)
async def test_ledger_shape_and_scope_validation(body):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
        base_url="http://provider",
    ) as http:
        with pytest.raises(ProviderUnavailable):
            await PaySwiftClient(http).ledger("R003")


def test_ledger_requires_identity_reference_and_amount():
    entry = ProviderPayout.model_validate(payout())
    ledger = (entry,)
    assert (
        match_payout(ledger, rider_id="R003", reference="quickdrop:test", amount=Decimal(25)).kind
        == "CONFIRMED"
    )
    assert (
        match_payout(ledger, rider_id="R003", reference="unrelated", amount=Decimal(25)).kind
        == "MISSING"
    )
    assert (
        match_payout(ledger, rider_id="R004", reference="quickdrop:test", amount=Decimal(25)).kind
        == "CONFLICT"
    )
    assert (
        match_payout(ledger, rider_id="R003", reference="quickdrop:test", amount=Decimal(26)).kind
        == "CONFLICT"
    )
    other = ProviderPayout.model_validate(payout())
    assert (
        match_payout(
            (entry, other), rider_id="R003", reference="quickdrop:test", amount=Decimal(25)
        ).kind
        == "CONFLICT"
    )
    assert (
        match_payout((), rider_id="R003", reference="quickdrop:test", amount=Decimal(25)).kind
        == "MISSING"
    )


def test_bounded_backoff_respects_retry_after():
    for attempt in range(1, 30):
        assert 0 < backoff(attempt) <= 300
        assert backoff(attempt, 600) == 600
    assert payswift.retry_after("12") == 12
    assert payswift.retry_after("nan") is None
    assert payswift.retry_after("invalid") is None
    later = format_datetime(datetime.now(UTC) + timedelta(seconds=30))
    assert 20 < payswift.retry_after(later) <= 30


@pytest.mark.parametrize("amount", [0, -1, True, 1.5, Decimal(25), 10001])
async def test_post_rejects_invalid_amount_before_network(amount):
    def unexpected(request):
        raise AssertionError("Invalid request must not reach network")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(unexpected), base_url="http://provider"
    ) as http:
        with pytest.raises(ValueError):
            await PaySwiftClient(http).post(
                rider_id="R003", amount=amount, reference="reference", idempotency_key="key"
            )
