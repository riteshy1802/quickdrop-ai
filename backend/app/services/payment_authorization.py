"""Deterministic authorization; no HTTP mutation and no LLM-selected amounts."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.integrations.payswift import PaySwiftClient, ProviderUnavailable
from app.models import Conversation, Dispute, OpsQueue, PaymentIntent, Rider
from app.repositories.trips import IST
from app.services import trace_service
from app.services.financial.calculator import exact_sum
from app.services.financial.reconciliation import reconcile
from app.services.financial.types import Allocation, ClaimRequest, ConfirmedPayment, PaymentEvidence
from app.services.payment_reconciliation import match_payout, reference_for
from app.services.payment_types import AuthorizationResult


class EvidenceUnavailable(ValueError):
    pass


AUTO_PAY_LIMIT = Decimal(200)


def item_snapshot(items):
    return sorted(
        [
            {
                "source_type": i.source_type,
                "source_id": i.source_id,
                "expected_amount": str(i.expected_amount),
                "actual_amount": str(i.actual_amount),
                "difference": str(i.difference),
            }
            for i in items
        ],
        key=lambda item: (item["source_type"], item["source_id"]),
    )


async def provider_evidence(session, rider_id, ledger):
    intents = list(
        await session.scalars(select(PaymentIntent).where(PaymentIntent.rider_id == rider_id))
    )
    by_reference = {reference_for(intent.id): intent for intent in intents}
    confirmed = []
    for payout in ledger:
        intent = by_reference.get(payout.reference)
        if intent is None or not intent.authorization:
            raise EvidenceUnavailable("Unattributed provider payment requires review")
        matched = match_payout(
            ledger,
            rider_id=rider_id,
            reference=payout.reference,
            amount=intent.amount,
            provider_id=intent.provider_payout_id,
        )
        if matched.kind != "CONFIRMED" or intent.status != "SUCCEEDED":
            raise EvidenceUnavailable("Prior payment must be reconciled before authorization")
        try:
            allocations = tuple(
                Allocation.model_validate(a) for a in intent.authorization["allocations"]
            )
            confirmed.append(
                ConfirmedPayment(
                    provider_payout_id=payout.payout_id,
                    intent_id=intent.id,
                    amount=intent.amount,
                    allocations=allocations,
                )
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise EvidenceUnavailable("Prior allocation evidence requires review") from exc
    for intent in intents:
        if intent.status == "SUCCEEDED" and not any(
            p.payout_id == intent.provider_payout_id for p in ledger
        ):
            raise EvidenceUnavailable("Previously confirmed payment missing from provider ledger")
    return PaymentEvidence(
        rider_id=rider_id, provider_history_complete=True, confirmed=tuple(confirmed)
    ), intents


def audit(session, dispute, result):
    trace_service.record(
        session,
        dispute.conversation_id,
        "decision",
        "payment_authorization",
        input={"dispute_id": dispute.id},
        output={
            "status": result.status,
            "reason": result.reason,
            "intent_id": result.intent_id,
            "queue_id": result.queue_id,
        },
    )
    return result


async def approval_queue(session, dispute, amount, reason, *, escalation=False):
    prior = await session.scalar(
        select(OpsQueue)
        .where(
            OpsQueue.dispute_id == dispute.id,
            OpsQueue.type == ("escalation" if escalation else "approval"),
            OpsQueue.status.in_(("PENDING", "IN_REVIEW")),
            OpsQueue.resolved_at.is_(None),
        )
        .order_by(OpsQueue.created_at, OpsQueue.id)
        .limit(1)
    )
    if prior is not None:
        if not escalation and prior.amount != amount:
            return audit(
                session, dispute, AuthorizationResult("BLOCKED", "Pending approval amount changed")
            )
        return audit(
            session,
            dispute,
            AuthorizationResult(
                "ESCALATED" if escalation else "APPROVAL_REQUIRED", reason, queue_id=prior.id
            ),
        )
    queue = OpsQueue(
        id=uuid4(),
        dispute_id=dispute.id,
        type="escalation" if escalation else "approval",
        status="PENDING",
        amount=None if escalation else amount,
        reason=reason,
    )
    session.add(queue)
    dispute.status = "ESCALATED" if escalation else "AWAITING_APPROVAL"
    conversation = await session.get(Conversation, dispute.conversation_id)
    conversation.status = "ESCALATED" if escalation else "AWAITING_APPROVAL"
    return audit(
        session,
        dispute,
        AuthorizationResult(
            "ESCALATED" if escalation else "APPROVAL_REQUIRED", reason, queue_id=queue.id
        ),
    )


async def authorize_payment(
    factory,
    client: PaySwiftClient,
    dispute_id,
    request: ClaimRequest,
    *,
    source_data_complete: bool,
    execution_guard=None,
):
    # Fetch provider data before locks. Caller supplies trusted identity and source coverage.
    try:
        ledger = await client.ledger(request.rider_id)
        ledger_error = None
    except ProviderUnavailable:
        ledger, ledger_error = (), "Provider history unavailable"
    async with factory() as session, session.begin():
        return await authorize_in_session(
            session,
            dispute_id,
            request,
            source_data_complete=source_data_complete,
            ledger=ledger,
            ledger_error=ledger_error,
            execution_guard=execution_guard,
        )


async def authorize_in_session(
    session,
    dispute_id,
    request,
    *,
    source_data_complete,
    ledger,
    ledger_error=None,
    execution_guard=None,
):
    """Same authorization path, caller owns atomic transaction and provider read."""
    rider = await session.scalar(
        select(Rider).where(Rider.rider_id == request.rider_id).with_for_update()
    )
    if rider is None:
        raise ValueError("Rider not found")
    if execution_guard is not None:
        await execution_guard(session)
    dispute = await session.scalar(
        select(Dispute)
        .where(Dispute.id == dispute_id, Dispute.rider_id == request.rider_id)
        .options(selectinload(Dispute.items))
        .with_for_update()
    )
    if dispute is None:
        raise ValueError("Dispute not found for trusted rider")
    existing = await session.scalar(
        select(PaymentIntent)
        .where(PaymentIntent.dispute_id == dispute.id)
        .order_by(PaymentIntent.created_at, PaymentIntent.id)
        .limit(1)
    )
    if existing is not None:
        return audit(
            session,
            dispute,
            AuthorizationResult("EXISTING", "Dispute already has an intent", existing.id),
        )
    if ledger_error:
        return audit(session, dispute, AuthorizationResult("BLOCKED", ledger_error))
    trace_service.record(
        session,
        dispute.conversation_id,
        "tool_call",
        "payswift_authorization_ledger",
        input={"rider_id": request.rider_id},
        output={"validated_entries": len(ledger)},
    )
    if (
        dispute.status not in {"VERIFIED", "AWAITING_APPROVAL"}
        or not dispute.items
        or dispute.verified_amount is None
    ):
        return audit(
            session,
            dispute,
            AuthorizationResult("BLOCKED", "Dispute must have verified item evidence"),
        )
    try:
        evidence, intents = await provider_evidence(session, request.rider_id, ledger)
    except EvidenceUnavailable as exc:
        return audit(session, dispute, AuthorizationResult("BLOCKED", str(exc)))
    result = await reconcile(
        session, request, source_data_complete=source_data_complete, evidence=evidence
    )
    expected_scope = {(item.source_type, item.source_id) for item in dispute.items}
    actual_scope = {(item.source_type, item.source_id) for item in result.items}
    if (
        not result.eligible
        or result.status != "VERIFIED"
        or result.requires_payment_reconciliation
        or result.outstanding is None
        or result.outstanding <= 0
        or result.verified_shortfall != dispute.verified_amount
        or expected_scope != actual_scope
        or len(expected_scope) != len(dispute.items)
    ):
        return audit(
            session,
            dispute,
            AuthorizationResult(
                "BLOCKED", "Fresh reconciliation does not verify complete dispute scope"
            ),
        )
    by_source = {(item.source_type, item.source_id): item for item in result.items}
    for item in dispute.items:
        current = by_source[(item.source_type, item.source_id)]
        if (
            item.expected_amount != current.expected_amount
            or item.actual_amount != current.historical_paid
            or item.difference != current.raw_difference
        ):
            return audit(
                session,
                dispute,
                AuthorizationResult("BLOCKED", "Stored item evidence differs from source records"),
            )
    amount = result.outstanding
    if not amount.is_finite() or amount != amount.to_integral_value():
        return audit(
            session,
            dispute,
            AuthorizationResult("BLOCKED", "Outstanding balance must be whole rupees"),
        )
    if amount > 10000:
        return await approval_queue(
            session,
            dispute,
            amount,
            "Full balance exceeds provider single-payment limit; no splitting",
            escalation=True,
        )
    approved = await session.scalar(
        select(OpsQueue)
        .where(
            OpsQueue.dispute_id == dispute.id,
            OpsQueue.type == "approval",
        )
        .order_by(OpsQueue.created_at.desc(), OpsQueue.id.desc())
        .limit(1)
    )
    if approved is not None and approved.status in {"REJECTED", "RESOLVED"}:
        return audit(
            session,
            dispute,
            AuthorizationResult("BLOCKED", "Prior Ops decision requires explicit new review"),
        )
    ops_authorized = (
        approved is not None
        and approved.status == "APPROVED"
        and approved.amount == amount
        and approved.assigned_to is not None
        and approved.resolved_at is not None
    )
    day = datetime.now(UTC).astimezone(IST).date()
    daily_reserved = any(i.payment_type == "AUTO" and i.auto_pay_date == day for i in intents)
    prior_auto_inflight = any(
        i.payment_type == "AUTO" and i.status in {"PENDING", "PROCESSING", "UNKNOWN"}
        for i in intents
    )
    # A provider-confirmed payout crossing midnight also consumes that observed IST day.
    auto_ids = {reference_for(i.id) for i in intents if i.payment_type == "AUTO"}
    daily_observed = any(
        p.reference in auto_ids and p.created_at.astimezone(IST).date() == day for p in ledger
    )
    needs_ops = (
        amount > AUTO_PAY_LIMIT
        or dispute.verified_amount > AUTO_PAY_LIMIT
        or daily_reserved
        or daily_observed
        or prior_auto_inflight
    )
    if approved is not None and approved.status == "APPROVED" and not ops_authorized:
        return audit(
            session,
            dispute,
            AuthorizationResult("BLOCKED", "Ops approval evidence or amount invalid"),
        )
    approval_reason = (
        "Daily automatic payment allowance already used or reserved"
        if (daily_reserved or daily_observed or prior_auto_inflight)
        and amount <= AUTO_PAY_LIMIT
        and dispute.verified_amount <= AUTO_PAY_LIMIT
        else "Full verified balance requires Ops approval: amount or daily auto-pay limit"
    )
    if approved is not None and approved.status in {"PENDING", "IN_REVIEW"}:
        return await approval_queue(session, dispute, amount, approval_reason)
    if needs_ops and not ops_authorized:
        return await approval_queue(
            session,
            dispute,
            amount,
            approval_reason,
        )
    identifier = uuid4()
    allocations = [
        Allocation(
            source_type=item.source_type,
            source_id=item.source_id,
            service_date=item.service_date,
            amount=item.outstanding,
        )
        for item in result.items
        if item.outstanding and item.outstanding > 0
    ]
    if exact_sum(a.amount for a in allocations) != amount:
        return audit(
            session,
            dispute,
            AuthorizationResult("BLOCKED", "Allocation total differs from outstanding balance"),
        )
    session.add(
        PaymentIntent(
            id=identifier,
            dispute_id=dispute.id,
            rider_id=request.rider_id,
            amount=amount,
            status="PENDING",
            idempotency_key=f"quickdrop-dispute:{dispute.id}",
            payment_type="OPS_APPROVED" if ops_authorized else "AUTO",
            auto_pay_date=None if ops_authorized else day,
            authorization={
                "version": 1,
                "request": request.model_dump(mode="json"),
                "amount": str(amount),
                "rider_id": request.rider_id,
                "verified_at": datetime.now(UTC).isoformat(),
                "received_at": request.received_at.isoformat(),
                "approval_id": str(approved.id) if ops_authorized else None,
                "items": item_snapshot(dispute.items),
                "allocations": [a.model_dump(mode="json") for a in allocations],
            },
        )
    )
    dispute.status = "PAYMENT_PENDING"
    conversation = await session.get(Conversation, dispute.conversation_id)
    conversation.status = "PAYMENT_PENDING"
    await session.flush()  # Unique idempotency and daily reservation are the final DB barriers.
    return audit(
        session,
        dispute,
        AuthorizationResult("AUTHORIZED", "Full outstanding balance reserved", identifier),
    )
