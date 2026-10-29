"""Single-attempt HTTP client. Durable retries belong to the payment worker."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache
from typing import Literal

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, ValidationError

from app.core.config import get_settings

REQUEST_BUDGET_SECONDS = 7


class ProviderUnavailable(Exception):
    """Provider data is unavailable or cannot be validated. Never include raw bodies."""


class ProviderPayout(BaseModel):
    model_config = ConfigDict(extra="ignore")
    payout_id: str = Field(pattern=r"^pout_[A-Za-z0-9_-]+$", max_length=255)
    rider_id: str = Field(min_length=1, max_length=32)
    amount: StrictInt = Field(ge=1, le=10000)
    reference: str = Field(min_length=1, max_length=255)
    status: Literal["processed"]
    created_at: AwareDatetime


class Ledger(BaseModel):
    data: list[ProviderPayout]
    count: StrictInt = Field(ge=0)


@dataclass(frozen=True)
class PostOutcome:
    kind: Literal["CONFIRMED", "REJECTED", "RATE_LIMITED", "AMBIGUOUS", "DEFERRED", "BLOCKED"]
    code: str
    http_status: int | None = None
    payout: ProviderPayout | None = None
    retry_after: float | None = None


def retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                return None
            seconds = (when - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    import math

    return max(0, seconds) if math.isfinite(seconds) else None


class PaySwiftClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.owned = client is None
        self.http = client or httpx.AsyncClient(
            base_url=get_settings().payswift_base_url,
            timeout=httpx.Timeout(5, connect=2, pool=2),
            follow_redirects=False,
            trust_env=False,
        )

    async def aclose(self):
        if self.owned:
            await self.http.aclose()

    async def health(self) -> bool:
        try:
            async with asyncio.timeout(REQUEST_BUDGET_SECONDS):
                response = await self.http.get("/health")
            return response.status_code == 200 and response.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError, AttributeError, TimeoutError):
            return False

    async def ledger(self, rider_id: str) -> tuple[ProviderPayout, ...]:
        try:
            async with asyncio.timeout(REQUEST_BUDGET_SECONDS):
                response = await self.http.get("/v1/payouts", params={"rider_id": rider_id})
            if response.status_code != 200:
                raise ProviderUnavailable("ledger_http_error")
            payload = Ledger.model_validate(response.json())
            if payload.count != len(payload.data) or any(
                p.rider_id != rider_id for p in payload.data
            ):
                raise ProviderUnavailable("ledger_scope_or_count_invalid")
            unique = {}
            for payout in payload.data:
                if payout.payout_id in unique and unique[payout.payout_id] != payout:
                    raise ProviderUnavailable("ledger_conflicting_identifier")
                unique[payout.payout_id] = payout
            return tuple(unique.values())
        except (httpx.HTTPError, ValueError, ValidationError, TimeoutError) as exc:
            raise ProviderUnavailable("ledger_unavailable_or_invalid") from exc

    async def post(
        self, *, rider_id: str, amount: int, reference: str, idempotency_key: str
    ) -> PostOutcome:
        if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= 10000:
            raise ValueError("PaySwift amount must be integer rupees between 1 and 10000")
        if not rider_id or not reference or not idempotency_key:
            raise ValueError("Payment identity and correlation fields are required")
        try:
            async with asyncio.timeout(REQUEST_BUDGET_SECONDS):
                response = await self.http.post(
                    "/v1/payouts",
                    json={
                        "rider_id": rider_id,
                        "amount": amount,
                        "reference": reference,
                    },
                    headers={"Idempotency-Key": idempotency_key},
                )
        except (httpx.HTTPError, TimeoutError):
            return PostOutcome("AMBIGUOUS", "transport_error")
        code = response.status_code
        if code == 201:
            try:
                payout = ProviderPayout.model_validate(response.json())
                if (payout.rider_id, payout.amount, payout.reference) != (
                    rider_id,
                    amount,
                    reference,
                ):
                    return PostOutcome("AMBIGUOUS", "response_correlation_mismatch", code)
                return PostOutcome("CONFIRMED", "provider_confirmed", code, payout)
            except (ValueError, ValidationError):
                return PostOutcome("AMBIGUOUS", "invalid_success_response", code)
        if code == 400:
            return PostOutcome("REJECTED", "provider_validation_rejected", code)
        if code == 429:
            return PostOutcome(
                "RATE_LIMITED",
                "provider_rate_limited",
                code,
                retry_after=retry_after(response.headers.get("Retry-After")),
            )
        # Includes 409, 5xx, redirects and unexpected codes. Never replay automatically.
        return PostOutcome("AMBIGUOUS", "provider_outcome_uncertain", code)


@lru_cache
def get_payswift_client() -> PaySwiftClient:
    return PaySwiftClient()
