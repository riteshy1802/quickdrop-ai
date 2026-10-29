"""Rider lock serializes Ops actions with all agent and payment side-effect boundaries."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import Conversation, Dispute, Message, OpsQueue, PaymentIntent
from app.services import conversation_service, trace_service


async def locked_conversation(session, identifier):
    rider = await session.scalar(select(Conversation.rider_id).where(Conversation.id == identifier))
    if rider is None:
        raise HTTPException(404, "Conversation not found")
    await conversation_service.lock_rider(session, rider)
    return await session.scalar(
        select(Conversation)
        .where(Conversation.id == identifier)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def audit(session, conversation, operator, action, *, reason=None, **output):
    trace_service.record(
        session,
        conversation.id,
        "decision",
        "ops_" + action,
        input={"operator_id": operator.id, "conversation_id": conversation.id, "reason": reason},
        output=output,
    )


def require_owner(conversation, operator):
    if conversation.status == "RESOLVED":
        raise HTTPException(409, "Conversation already resolved")
    if conversation.handling_mode != "HUMAN" or conversation.assigned_operator_id != operator.id:
        raise HTTPException(409, "Take over this conversation before acting")


async def blockers(session, conversation):
    disputes = list(
        await session.scalars(select(Dispute).where(Dispute.conversation_id == conversation.id))
    )
    ids = [d.id for d in disputes]
    pending = await session.scalar(
        select(OpsQueue.id)
        .where(OpsQueue.dispute_id.in_(ids), OpsQueue.status.in_(("PENDING", "IN_REVIEW")))
        .limit(1)
    )
    if pending:
        return "Unresolved approval or escalation requires human review"
    if await session.scalar(
        select(PaymentIntent.id)
        .where(
            PaymentIntent.rider_id == conversation.rider_id,
            PaymentIntent.status.in_(
                ("PENDING", "PROCESSING", "UNKNOWN", "NEEDS_REVIEW", "AWAITING_APPROVAL")
            ),
        )
        .limit(1)
    ):
        return "Payment is pending or uncertain; reconcile before proceeding"
    if any(
        d.status in {"OPEN", "INVESTIGATING", "ESCALATED", "AWAITING_APPROVAL", "PAYMENT_PENDING"}
        for d in disputes
    ):
        return "Sensitive investigation remains unresolved"
    if any(
        conversation.context.get(key)
        for key in ("identity_concern", "security_concern", "sensitive_investigation")
    ):
        return "Identity, security or sensitive investigation requires review"
    return None


async def stop_pending_agent_work(session, conversation):
    # Persist a stable acknowledgement for old claims, including across later handback.
    from app.services.message_service import HUMAN_REPLY

    rows = await session.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.processing_status.in_(("RECEIVED", "PROCESSING", "FAILED")),
        )
        .with_for_update()
    )
    for message in rows:
        message.processing_status = "COMPLETED"
        message.webhook_reply = HUMAN_REPLY
        message.processing_token = message.processing_expires_at = message.next_processing_at = None


async def transition(factory, identifier, operator, action, reason=None):
    async with factory() as session, session.begin():
        conversation = await locked_conversation(session, identifier)
        if action == "takeover":
            if conversation.status == "RESOLVED" or conversation.handling_mode != "AI":
                raise HTTPException(409, "Conversation not eligible for takeover")
            conversation.handling_mode = "HUMAN"
            conversation.status = "HUMAN_HANDLING"
            conversation.assigned_operator_id = operator.id
            conversation.control_version += 1
            await stop_pending_agent_work(session, conversation)
        else:
            require_owner(conversation, operator)
            blocked = await blockers(session, conversation)
            if blocked:
                raise HTTPException(409, blocked)
            conversation.control_version += 1
            if action == "handoff":
                conversation.handling_mode, conversation.status = "AI", "OPEN"
                conversation.assigned_operator_id = None
            elif action == "resolve":
                conversation.status = "RESOLVED"
            else:
                raise ValueError("Unknown action")
            await stop_pending_agent_work(session, conversation)
        conversation.updated_at = datetime.now(UTC)
        audit(
            session,
            conversation,
            operator,
            action,
            reason=reason,
            handling_mode=conversation.handling_mode,
            status=conversation.status,
        )
        return {
            "id": conversation.id,
            "status": conversation.status,
            "handling_mode": conversation.handling_mode,
            "assigned_operator_id": conversation.assigned_operator_id,
            "control_version": conversation.control_version,
        }


async def post_message(factory, identifier, operator, payload, *, internal=False):
    async with factory() as session, session.begin():
        conversation = await locked_conversation(session, identifier)
        # Serialize keys across conversations, too; prevents concurrent key reuse races.
        await session.execute(
            select(func.pg_advisory_xact_lock(payload.client_request_id.int % (2**63 - 1)))
        )
        prior = await session.scalar(
            select(Message).where(Message.client_request_id == payload.client_request_id)
        )
        if prior is not None:
            if (
                prior.conversation_id != identifier
                or prior.operator_id != operator.id
                or prior.content != payload.text
                or prior.is_internal != internal
            ):
                raise HTTPException(409, "Client request ID reused with different content")
            return conversation_service.message_response(prior)
        if internal:
            if conversation.status == "RESOLVED":
                raise HTTPException(409, "Conversation already resolved")
        else:
            require_owner(conversation, operator)
        message = Message(
            id=uuid4(),
            conversation_id=identifier,
            sender_type="OPS",
            content=payload.text,
            is_internal=internal,
            operator_id=operator.id,
            client_request_id=payload.client_request_id,
            created_at=datetime.now(UTC),
        )
        session.add(message)
        conversation.updated_at = datetime.now(UTC)
        audit(
            session,
            conversation,
            operator,
            "internal_note" if internal else "human_message",
            message_id=message.id,
            visibility="INTERNAL" if internal else "RIDER",
        )
        # Private text is deliberately absent from publicly readable assignment traces.
        return conversation_service.message_response(message)
