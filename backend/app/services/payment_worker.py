"""One durable job per call. Ownership tokens fence late worker responses."""

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.integrations.payswift import PostOutcome, ProviderUnavailable
from app.models import Conversation, Dispute, OpsQueue, PaymentIntent
from app.repositories.payment_jobs import claim_job, escalate
from app.repositories.trips import IST
from app.services import conversation_service, trace_service
from app.services.payment_reconciliation import match_payout, reconcile_job
from app.services.payment_types import ReconcileOutcome


def backoff(attempt: int, retry_after: float | None = None) -> float:
    delay = min(300, (2 ** min(attempt, 8)) * random.uniform(0.8, 1.2))
    return max(delay, retry_after or 0)


async def finish(factory, job, outcome, *, max_attempts, manual=False):
    async with factory() as session, session.begin():
        # Same outer lock as Ops and agent mutations prevents lock-order inversions.
        await conversation_service.lock_rider(session, job.rider_id)
        intent = await session.scalar(
            select(PaymentIntent).where(PaymentIntent.id == job.id).with_for_update()
        )
        if intent.processing_token != job.token:
            return None  # A recovered owner is authoritative; never overwrite its state.
        now = datetime.now(UTC)
        delay = backoff(
            job.attempt, outcome.retry_after if isinstance(outcome, PostOutcome) else None
        )
        confirmed = outcome.kind == "CONFIRMED"
        if confirmed:
            provider_id = (
                outcome.payout.payout_id if isinstance(outcome, PostOutcome) else outcome.payout_id
            )
            collision = await session.scalar(
                select(PaymentIntent.id)
                .where(
                    PaymentIntent.provider_payout_id == provider_id,
                    PaymentIntent.id != job.id,
                )
                .limit(1)
            )
            if collision is not None:
                outcome = ReconcileOutcome("CONFLICT", "provider_identifier_already_attributed")
                confirmed = False
        if confirmed:
            intent.status = "SUCCEEDED"
            intent.provider_payout_id = (
                outcome.payout.payout_id if isinstance(outcome, PostOutcome) else outcome.payout_id
            )
        elif job.original_status == "SUCCEEDED":
            intent.status = "SUCCEEDED"  # Ledger reset must not erase a known completed transfer.
        elif isinstance(outcome, PostOutcome):
            if outcome.kind == "REJECTED":
                intent.status = "FAILED"
            elif outcome.kind in {"RATE_LIMITED", "DEFERRED"}:
                if delay > 86400 or job.attempt >= max_attempts:
                    intent.status = "NEEDS_REVIEW"
                else:
                    intent.status = "PENDING"
                    # Provider 429 or a deferred preflight proves this owner has not sent money.
                    intent.post_started_at = None
            elif outcome.kind == "BLOCKED":
                intent.status = "NEEDS_REVIEW"
            else:
                intent.status = "UNKNOWN" if job.attempt < max_attempts else "NEEDS_REVIEW"
        elif outcome.kind == "CONFLICT":
            intent.status = "NEEDS_REVIEW"
        elif manual and job.original_status in {"FAILED", "NEEDS_REVIEW", "AWAITING_APPROVAL"}:
            intent.status = job.original_status
        elif manual and job.original_status == "PENDING" and job.never_sent:
            intent.status = "PENDING"
        else:
            intent.status = "UNKNOWN" if job.attempt < max_attempts else "NEEDS_REVIEW"
        if isinstance(outcome, ReconcileOutcome) and outcome.at is not None:
            intent.last_reconciled_at = outcome.at
        intent.processing_token = None
        intent.lease_expires_at = None
        intent.next_retry_at = (
            now + timedelta(seconds=delay) if intent.status in {"PENDING", "UNKNOWN"} else None
        )
        dispute = await session.get(Dispute, job.dispute_id)
        if confirmed:
            dispute.status = "RESOLVED"
            others = await session.scalar(
                select(func.count())
                .select_from(Dispute)
                .where(
                    Dispute.conversation_id == job.conversation_id,
                    Dispute.id != dispute.id,
                    Dispute.status.not_in(("RESOLVED", "REJECTED")),
                )
            )
            if not others:
                conversation = await session.get(Conversation, job.conversation_id)
                pending_case = await session.scalar(
                    select(OpsQueue.id)
                    .join(Dispute, Dispute.id == OpsQueue.dispute_id)
                    .where(
                        Dispute.conversation_id == job.conversation_id,
                        OpsQueue.status.in_(("PENDING", "IN_REVIEW")),
                    )
                    .limit(1)
                )
                if conversation.handling_mode == "AI" and pending_case is None:
                    conversation.status = "RESOLVED"
        elif intent.status in {"FAILED", "NEEDS_REVIEW"}:
            await escalate(session, dispute, f"Payment requires review: {outcome.code}")
        trace_service.record(
            session,
            job.conversation_id,
            "tool_call",
            "payswift_request_result",
            input={"intent_id": job.id, "operation": job.operation, "attempt": job.attempt},
            output={
                "outcome": outcome.code,
                "status": intent.status,
                "provider_payout_id": intent.provider_payout_id,
                "http_status": outcome.http_status if isinstance(outcome, PostOutcome) else None,
                "next_retry_at": intent.next_retry_at,
            },
        )
        return intent.status


async def execute_job(factory, client, job, *, max_attempts, manual=False):
    if job.operation == "POST":
        if (
            job.payment_type == "AUTO"
            and job.auto_pay_date != datetime.now(UTC).astimezone(IST).date()
        ):
            # Initiation crossed midnight after claim. No network mutation is made.
            outcome = PostOutcome("REJECTED", "reserved_ist_day_expired")
        else:
            outcome = await dispatch_preflight(factory, client, job)
            if (
                outcome is None
                and job.payment_type == "AUTO"
                and job.auto_pay_date != datetime.now(UTC).astimezone(IST).date()
            ):
                outcome = PostOutcome("BLOCKED", "reserved_ist_day_expired")
            if outcome is None:
                outcome = await client.post(
                    rider_id=job.rider_id,
                    amount=int(job.amount),
                    reference=job.reference,
                    idempotency_key=job.idempotency_key,
                )
    else:
        outcome = await reconcile_job(client, job, job.provider_id)
    return await finish(factory, job, outcome, max_attempts=max_attempts, manual=manual)


async def process_one(factory, client, *, max_attempts=None):
    attempts = max_attempts or get_settings().payment_max_attempts
    job = await claim_job(factory, max_attempts=attempts)
    if job is None:
        return False
    await execute_job(factory, client, job, max_attempts=attempts)
    return True


async def reconcile_intent(factory, client, identifier):
    attempts = get_settings().payment_max_attempts
    job = await claim_job(factory, max_attempts=attempts, identifier=identifier, manual=True)
    return await execute_job(factory, client, job, max_attempts=attempts, manual=True)


async def dispatch_preflight(factory, client, job):
    """Recheck current source balances and provider history immediately before POST."""
    from app.data_quality.normalize import prepare_trip
    from app.repositories import financial
    from app.repositories.payment_jobs import LEASE_SECONDS, valid_authorization
    from app.services.financial.reconciliation import reconcile_records
    from app.services.financial.types import (
        Allocation,
        ClaimRequest,
        FinancialSnapshot,
        PayoutRecord,
        PriorClaim,
        PriorIntent,
        PriorItem,
        TripRecord,
    )
    from app.services.payment_authorization import EvidenceUnavailable, provider_evidence

    try:
        ledger = await client.ledger(job.rider_id)
        ledger_error = False
    except ProviderUnavailable:
        ledger, ledger_error = (), True
    async with factory() as session, session.begin():
        intent = await session.scalar(
            select(PaymentIntent).where(PaymentIntent.id == job.id).with_for_update()
        )
        if intent.processing_token != job.token:
            return PostOutcome("BLOCKED", "dispatch_ownership_lost")
        trace_service.record(
            session,
            job.conversation_id,
            "tool_call",
            "payswift_dispatch_ledger",
            input={"intent_id": job.id, "rider_id": job.rider_id},
            output={"available": not ledger_error, "validated_entries": len(ledger)},
        )
        if ledger_error:
            return PostOutcome("DEFERRED", "dispatch_ledger_unavailable_no_post")
        own_match = match_payout(
            ledger,
            rider_id=job.rider_id,
            reference=job.reference,
            amount=job.amount,
            provider_id=job.provider_id,
        )
        if own_match.kind == "CONFIRMED":
            return own_match
        if own_match.kind == "CONFLICT":
            return PostOutcome("BLOCKED", own_match.code)
        from sqlalchemy.orm import selectinload

        dispute = await session.scalar(
            select(Dispute).where(Dispute.id == job.dispute_id).options(selectinload(Dispute.items))
        )
        if not valid_authorization(intent, dispute):
            return PostOutcome("BLOCKED", "dispatch_authorization_changed")
        try:
            request = ClaimRequest.model_validate(intent.authorization["request"])
            if request.rider_id != job.rider_id:
                return PostOutcome("BLOCKED", "dispatch_identity_changed")
            evidence, _ = await provider_evidence(session, job.rider_id, ledger)
            days = sorted(set(request.trip_dates + request.penalty_dates + request.incentive_dates))
            records = await financial.trips_for_scope(session, job.rider_id, request.trip_ids, days)
            own_ids = [trip.trip_id for trip in records if trip.rider_id == job.rider_id]
            payouts = await financial.payouts_for_scope(session, job.rider_id, own_ids, days)
            claims = await financial.prior_claims(session, job.rider_id)
            prepared = [prepare_trip(TripRecord.model_validate(trip)) for trip in records]
            snapshot = FinancialSnapshot(
                rider_exists=True,
                source_data_complete=True,
                trips=tuple(trip for trip, _ in prepared),
                trip_quality=tuple(quality for _, quality in prepared),
                payouts=tuple(PayoutRecord.model_validate(line) for line in payouts),
                prior_claims=tuple(
                    PriorClaim(
                        id=claim.id,
                        status=claim.status,
                        items=tuple(
                            PriorItem(source_type=item.source_type, source_id=item.source_id)
                            for item in claim.items
                        ),
                        intents=tuple(
                            PriorIntent(
                                id=p.id,
                                status=p.status,
                                amount=p.amount,
                                provider_payout_id=p.provider_payout_id,
                            )
                            for p in claim.payment_intents
                            if p.id != job.id
                        ),
                    )
                    for claim in claims
                ),
            )
            result = reconcile_records(request, snapshot, evidence)
            current = {(item.source_type, item.source_id): item for item in result.items}
            allocations = [
                Allocation.model_validate(value) for value in intent.authorization["allocations"]
            ]
            verified = (
                result.eligible
                and result.status == "VERIFIED"
                and result.outstanding == job.amount
                and result.verified_shortfall == dispute.verified_amount
                and all(
                    (entry := current.get((a.source_type, a.source_id))) is not None
                    and entry.outstanding is not None
                    and a.amount <= entry.outstanding
                    for a in allocations
                )
            )
        except (EvidenceUnavailable, KeyError, ValueError, TypeError):
            verified = False
        trace_service.record(
            session,
            job.conversation_id,
            "decision",
            "payment_dispatch_verification",
            input={"intent_id": job.id},
            output={"verified": verified},
        )
        if not verified:
            return PostOutcome("BLOCKED", "dispatch_outstanding_balance_not_verified")
        intent.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
    return None
