"""Atomic Ops queue decisions reuse the existing financial authorization path."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select

from app.agent.tools.coverage import source_coverage
from app.integrations.payswift import ProviderUnavailable
from app.models import Dispute, OpsQueue, OpsUser, PaymentIntent
from app.services.financial.types import ClaimRequest
from app.services.human_handoff_service import audit, locked_conversation
from app.services.payment_authorization import authorize_in_session


async def act(factory, identifier, operator, action, *, reason=None, operator_id=None, client=None):
    # Read identity and provider evidence before acquiring transactional locks.
    async with factory() as session:
        conversation_id = await session.scalar(
            select(Dispute.conversation_id)
            .join(OpsQueue, OpsQueue.dispute_id == Dispute.id)
            .where(OpsQueue.id == identifier)
        )
        if conversation_id is None:
            raise HTTPException(404, "Case not found")
        rider_id = await session.scalar(
            select(Dispute.rider_id)
            .join(OpsQueue, OpsQueue.dispute_id == Dispute.id)
            .where(OpsQueue.id == identifier)
        )
    ledger = ()
    if action == "approve":
        try:
            ledger = await client.ledger(rider_id)
        except ProviderUnavailable as exc:
            raise HTTPException(
                409, "Provider history unavailable; reconcile before approval"
            ) from exc
    async with factory() as session, session.begin():
        conversation = await locked_conversation(session, conversation_id)
        dispute = await session.scalar(
            select(Dispute)
            .join(OpsQueue, OpsQueue.dispute_id == Dispute.id)
            .where(OpsQueue.id == identifier)
            .with_for_update(of=Dispute)
        )
        case = await session.scalar(
            select(OpsQueue).where(OpsQueue.id == identifier).with_for_update()
        )
        if conversation.status == "RESOLVED":
            raise HTTPException(409, "Conversation already resolved")
        if case.status not in {"PENDING", "IN_REVIEW"}:
            raise HTTPException(409, "Case already decided")
        if case.assigned_to is not None and case.assigned_to != operator.id:
            raise HTTPException(409, "Case assigned to another operator")
        intent_id = None
        if action in {"approve", "reject"}:
            if case.type != "approval":
                raise HTTPException(409, "Case is not a financial approval")
            if await session.scalar(
                select(PaymentIntent.id).where(PaymentIntent.dispute_id == dispute.id).limit(1)
            ):
                raise HTTPException(409, "Dispute already has a payment intent; reconcile it")
            if dispute.status not in {"VERIFIED", "AWAITING_APPROVAL"}:
                raise HTTPException(409, "Dispute no longer eligible for approval")
            case.status = "APPROVED" if action == "approve" else "REJECTED"
            case.assigned_to, case.resolved_at, case.decision_note = (
                operator.id,
                datetime.now(UTC),
                reason,
            )
            if action == "approve":
                if await session.scalar(
                    select(PaymentIntent.id)
                    .where(
                        PaymentIntent.rider_id == rider_id,
                        PaymentIntent.status.in_(
                            (
                                "PENDING",
                                "PROCESSING",
                                "UNKNOWN",
                                "NEEDS_REVIEW",
                                "AWAITING_APPROVAL",
                            )
                        ),
                    )
                    .limit(1)
                ):
                    raise HTTPException(409, "Existing rider payment requires reconciliation")
                if not case.amount or case.amount != dispute.verified_amount:
                    raise HTTPException(409, "Approval amount differs from verified dispute")
                try:
                    request = ClaimRequest.model_validate(dispute.details["request"])
                except (KeyError, ValueError, TypeError) as exc:
                    raise HTTPException(
                        409, "Stored trusted claim scope missing or invalid"
                    ) from exc
                if request.rider_id != rider_id:
                    raise HTTPException(409, "Stored claim identity does not match dispute")
                await session.flush()
                coverage = await source_coverage(session, request)
                result = await authorize_in_session(
                    session, dispute.id, request, source_data_complete=coverage, ledger=ledger
                )
                if result.status != "AUTHORIZED":
                    raise HTTPException(409, result.reason)
                intent_id = result.intent_id
            else:
                dispute.status = "REJECTED"
        elif action in {"assign", "resolve"}:
            if case.type != "escalation":
                raise HTTPException(409, "Case is not an escalation")
            if action == "assign":
                target = operator_id or operator.id
                if await session.get(OpsUser, target) is None:
                    raise HTTPException(404, "Operator not found")
                if case.assigned_to is not None:
                    raise HTTPException(409, "Escalation already assigned")
                case.assigned_to, case.status = target, "IN_REVIEW"
            else:
                if case.status != "IN_REVIEW" or case.assigned_to != operator.id:
                    raise HTTPException(409, "Assign escalation to yourself before resolving")
                case.status, case.resolved_at, case.decision_note = (
                    "RESOLVED",
                    datetime.now(UTC),
                    reason,
                )
                dispute.status = "RESOLVED"
        else:
            raise ValueError("Unknown action")
        audit(
            session,
            conversation,
            operator,
            "case_" + action,
            reason=reason,
            case_id=case.id,
            dispute_id=dispute.id,
            status=case.status,
            assigned_to=case.assigned_to,
            intent_id=intent_id,
        )
        return {
            "id": case.id,
            "status": case.status,
            "assigned_to": case.assigned_to,
            "resolved_at": case.resolved_at,
            "decision_note": case.decision_note,
            "payment_intent_id": intent_id,
            "payment_confirmed": False,
        }
