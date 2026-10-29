"""Short transactions claim durable work; HTTP never runs in this module."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.models import Dispute, OpsQueue, PaymentIntent
from app.repositories.trips import IST
from app.services import trace_service
from app.services.financial.calculator import exact_sum
from app.services.financial.types import Allocation
from app.services.payment_authorization import item_snapshot
from app.services.payment_reconciliation import reference_for
from app.services.payment_types import PaymentJob

LEASE_SECONDS = 60


class PaymentBusy(Exception):
    pass


def valid_authorization(intent, dispute):
    data = intent.authorization
    if not data or data.get("version") != 1 or data.get("rider_id") != intent.rider_id:
        return False
    try:
        allocations = [Allocation.model_validate(value) for value in data["allocations"]]
        keys = [(a.source_type, a.source_id) for a in allocations]
        scope = {(i.source_type, i.source_id): max(Decimal(0), i.difference) for i in dispute.items}
        return (
            Decimal(data["amount"]) == intent.amount
            and exact_sum(a.amount for a in allocations) == intent.amount
            and len(keys) == len(set(keys))
            and bool(keys)
            and all(
                key in scope and amount.amount <= scope[key]
                for key, amount in zip(keys, allocations, strict=True)
            )
            and data["items"] == item_snapshot(dispute.items)
            and dispute.verified_amount is not None
            and intent.amount <= dispute.verified_amount
            and dispute.status == "PAYMENT_PENDING"
            and 1 <= intent.amount <= 10000
        )
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return False


async def escalate(session, dispute, reason):
    existing = await session.scalar(
        select(OpsQueue.id)
        .where(
            OpsQueue.dispute_id == dispute.id,
            OpsQueue.type == "escalation",
            OpsQueue.status.in_(("PENDING", "IN_REVIEW")),
            OpsQueue.resolved_at.is_(None),
        )
        .limit(1)
    )
    if existing is None:
        session.add(
            OpsQueue(
                id=uuid4(),
                dispute_id=dispute.id,
                type="escalation",
                status="PENDING",
                reason=reason,
            )
        )


async def claim_job(factory, *, max_attempts: int, identifier=None, manual=False):
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        statement = select(PaymentIntent)
        if identifier is None:
            statement = statement.where(
                or_(
                    and_(
                        PaymentIntent.status.in_(("PENDING", "UNKNOWN")),
                        or_(
                            PaymentIntent.next_retry_at.is_(None),
                            PaymentIntent.next_retry_at <= now,
                        ),
                        or_(
                            PaymentIntent.lease_expires_at.is_(None),
                            PaymentIntent.lease_expires_at <= now,
                        ),
                    ),
                    and_(
                        PaymentIntent.status == "PROCESSING",
                        or_(
                            PaymentIntent.lease_expires_at.is_(None),
                            PaymentIntent.lease_expires_at <= now,
                        ),
                    ),
                )
            )
        else:
            statement = statement.where(PaymentIntent.id == identifier)
        intent = await session.scalar(
            statement.order_by(PaymentIntent.created_at, PaymentIntent.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if intent is None:
            if identifier is not None:
                if await session.get(PaymentIntent, identifier) is None:
                    raise LookupError("Payout not found")
                raise PaymentBusy("Payout is busy")
            return None
        if intent.lease_expires_at and intent.lease_expires_at > now:
            if manual:
                raise PaymentBusy("Payout is busy")
            return None
        dispute = await session.scalar(
            select(Dispute)
            .where(Dispute.id == intent.dispute_id)
            .options(selectinload(Dispute.items))
        )
        old_status = intent.status
        if not manual and intent.retry_count >= max_attempts:
            intent.status = "NEEDS_REVIEW"
            intent.next_retry_at = None
            intent.processing_token = None
            intent.lease_expires_at = None
            await escalate(session, dispute, "Payment attempt budget exhausted")
            trace_service.record(
                session,
                dispute.conversation_id,
                "error",
                "payment_attempt_budget_exhausted",
                input={"intent_id": intent.id},
                output={"status": intent.status},
            )
            return None
        never_sent = intent.post_started_at is None and intent.provider_payout_id is None
        operation = "POST" if not manual and old_status == "PENDING" and never_sent else "RECONCILE"
        approval_valid = True
        if operation == "POST" and intent.payment_type == "OPS_APPROVED":
            try:
                from uuid import UUID

                approval_id = UUID((intent.authorization or {})["approval_id"])
                approval = await session.get(OpsQueue, approval_id)
                approval_valid = bool(
                    approval
                    and approval.dispute_id == dispute.id
                    and approval.type == "approval"
                    and approval.status == "APPROVED"
                    and approval.amount == intent.amount
                    and approval.assigned_to is not None
                    and approval.resolved_at is not None
                )
            except (KeyError, TypeError, ValueError):
                approval_valid = False
        if operation == "POST" and (
            not valid_authorization(intent, dispute)
            or not approval_valid
            or (
                intent.payment_type == "AUTO"
                and (dispute.verified_amount is None or dispute.verified_amount > 200)
            )
            or (
                intent.payment_type == "AUTO" and intent.auto_pay_date != now.astimezone(IST).date()
            )
        ):
            intent.status = "NEEDS_REVIEW"
            intent.next_retry_at = None
            await escalate(
                session,
                dispute,
                "Payment authorization invalid, changed, or outside reserved IST day",
            )
            trace_service.record(
                session,
                dispute.conversation_id,
                "error",
                "payment_authorization_recheck_failed",
                input={"intent_id": intent.id},
                output={"status": intent.status},
            )
            return None
        token = uuid4()
        # Already confirmed payments remain confirmed during a manual GET or a crash.
        intent.status = "SUCCEEDED" if old_status == "SUCCEEDED" else "PROCESSING"
        intent.processing_token = token
        intent.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        intent.retry_count += 1
        intent.next_retry_at = None
        if operation == "POST":
            # Committed before HTTP: a crash from this point can only recover via GET.
            intent.post_started_at = now
        trace_service.record(
            session,
            dispute.conversation_id,
            "tool_call",
            "payswift_request_started",
            input={
                "intent_id": intent.id,
                "operation": operation,
                "attempt": intent.retry_count,
                "rider_id": intent.rider_id,
                "reference": reference_for(intent.id),
                "amount": intent.amount,
            },
            output=None,
            at=now,
        )
        return PaymentJob(
            id=intent.id,
            rider_id=intent.rider_id,
            conversation_id=dispute.conversation_id,
            dispute_id=dispute.id,
            amount=intent.amount,
            idempotency_key=intent.idempotency_key,
            reference=reference_for(intent.id),
            token=token,
            operation=operation,
            attempt=intent.retry_count,
            original_status=old_status,
            never_sent=never_sent,
            provider_id=intent.provider_payout_id,
            auto_pay_date=intent.auto_pay_date,
            payment_type=intent.payment_type,
        )
