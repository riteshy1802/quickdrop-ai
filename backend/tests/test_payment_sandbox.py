"""Explicit opt-in sandbox integration; uses only the disposable PostgreSQL fixture."""

import asyncio
import os
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
import pytest
from test_payments_database import create_case, view
from test_payments_database import payments as payments

from app.integrations.payswift import PaySwiftClient
from app.services.payment_authorization import authorize_payment
from app.services.payment_worker import process_one, reconcile_intent

pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(
        os.getenv("QUICKDROP_RUN_SANDBOX_TEST") != "1",
        reason="Sandbox payments require explicit opt-in",
    ),
]


async def test_real_sandbox_round_trip(payments):
    url = os.environ.get("PAYSWIFT_BASE_URL", "http://127.0.0.1:8081")
    parsed = urlsplit(url)
    assert parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    assert parsed.port == 8081 and not parsed.username and not parsed.password
    factory, rider, _ = payments
    async with httpx.AsyncClient(base_url=url, timeout=5, trust_env=False) as http:
        client = PaySwiftClient(http)
        assert await client.health()
        dispute, request = await create_case(factory, rider, 25)
        authorization = await authorize_payment(
            factory, client, dispute, request, source_data_complete=True
        )
        assert authorization.status == "AUTHORIZED"
        async with asyncio.timeout(120):
            while True:
                await process_one(factory, client)
                intent = await view(factory, authorization.intent_id)
                if intent.status == "SUCCEEDED":
                    break
                assert intent.status in {"PENDING", "UNKNOWN"}, (
                    f"Sandbox outcome requires review: {intent.status}"
                )
                wait = (
                    max(0.1, (intent.next_retry_at - datetime.now(UTC)).total_seconds())
                    if intent.next_retry_at
                    else 0.1
                )
                await asyncio.sleep(wait)
        assert await reconcile_intent(factory, client, intent.id) == "SUCCEEDED"
        ledger = await client.ledger(rider)
        assert len(ledger) == 1 and ledger[0].payout_id == intent.provider_payout_id
        assert ledger[0].amount == 25
        persisted = await view(factory, intent.id)
        assert persisted.status == "SUCCEEDED" and persisted.last_reconciled_at is not None
        assert not await process_one(factory, client)
