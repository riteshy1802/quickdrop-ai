"""A missing in-memory ledger entry is never proof of non-execution."""

from datetime import UTC, datetime

from app.integrations.payswift import PaySwiftClient, ProviderPayout, ProviderUnavailable
from app.services.payment_types import PaymentJob, ReconcileOutcome


def reference_for(identifier) -> str:
    return f"quickdrop:{identifier}"


def match_payout(
    ledger: tuple[ProviderPayout, ...], *, rider_id, reference, amount, provider_id=None
):
    candidates = [
        p
        for p in ledger
        if p.reference == reference or (provider_id and p.payout_id == provider_id)
    ]
    if not candidates:
        return ReconcileOutcome("MISSING", "ledger_entry_missing", at=datetime.now(UTC))
    if len(candidates) != 1:
        return ReconcileOutcome("CONFLICT", "multiple_correlated_payouts", at=datetime.now(UTC))
    payout = candidates[0]
    if (payout.rider_id, payout.reference, payout.amount) != (rider_id, reference, amount) or (
        provider_id is not None and payout.payout_id != provider_id
    ):
        return ReconcileOutcome("CONFLICT", "ledger_correlation_mismatch", at=datetime.now(UTC))
    return ReconcileOutcome("CONFIRMED", "ledger_confirmed", payout.payout_id, datetime.now(UTC))


async def reconcile_job(client: PaySwiftClient, job: PaymentJob, provider_id=None):
    try:
        ledger = await client.ledger(job.rider_id)
    except ProviderUnavailable:
        return ReconcileOutcome("UNAVAILABLE", "ledger_unavailable")
    return match_payout(
        ledger,
        rider_id=job.rider_id,
        reference=job.reference,
        amount=job.amount,
        provider_id=provider_id,
    )
