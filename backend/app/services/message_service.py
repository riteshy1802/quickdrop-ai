"""Durable webhook claim, processing outside transactions, atomic completion."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from app.agent.nodes import AgentDeferred
from app.agent.tools import OwnershipLost
from app.core.config import get_settings
from app.models import Conversation, Message
from app.repositories import messages
from app.schemas.messages import IncomingMessage
from app.services import conversation_service, trace_service

logger = logging.getLogger(__name__)
LEASE_SECONDS = 30
WEBHOOK_TIMEOUT_SECONDS = 8
AI_REPLY = (
    "Your payout concern has been received. Please share the trip ID, date, and payout "
    "details so support can review it."
)
HUMAN_REPLY = "Your message has been forwarded to our support team."


class ProcessingBusy(Exception):
    pass


@dataclass(frozen=True)
class Claim:
    message_id: UUID
    conversation_id: UUID
    rider_id: str
    token: UUID
    handling_mode: str
    control_version: int = 0


def advisory_key(external_id: str) -> int:
    return int.from_bytes(
        hashlib.blake2b(("quickdrop:webhook:" + external_id).encode(), digest_size=8).digest(),
        "big",
        signed=True,
    )


async def transaction_limits(session):
    await session.execute(text("SET LOCAL lock_timeout = '1500ms'"))
    await session.execute(text("SET LOCAL statement_timeout = '2500ms'"))


def check_payload(message, rider_id, payload):
    if (
        (payload.conversation_id is not None and message.conversation_id != payload.conversation_id)
        or rider_id != payload.rider_id
        or message.content != payload.text
        or message.received_at != payload.received_at
    ):
        raise HTTPException(status_code=409, detail="Message ID reused with conflicting payload")


async def claim(
    factory, payload: IncomingMessage, *, from_worker=False, interactive_demo=False
) -> Claim | str:
    async with factory() as session, session.begin():
        await transaction_limits(session)
        owned = await session.scalar(
            select(func.pg_try_advisory_xact_lock(advisory_key(payload.message_id)))
        )
        if not owned:
            raise ProcessingBusy
        # The rider row serializes creation for different messages from the same rider.
        if await conversation_service.lock_rider(session, payload.rider_id) is None:
            raise HTTPException(status_code=404, detail="Rider not found")
        existing = await messages.webhook(session, payload.message_id)
        now = datetime.now(UTC)
        if existing:
            message, rider_id = existing
            check_payload(message, rider_id, payload)
            if message.processing_status == "COMPLETED":
                if message.webhook_reply is None:
                    raise HTTPException(status_code=503, detail="Stored reply unavailable")
                return message.webhook_reply
            if (
                not from_worker
                and message.webhook_reply is not None
                and message.agent_state is not None
            ):
                return message.webhook_reply
            if (
                message.processing_status == "PROCESSING"
                and message.processing_expires_at
                and message.processing_expires_at > now
            ):
                raise ProcessingBusy
            # Expired/failed/received work is recoverable. No duplicate input trace.
            conversation = await session.get(Conversation, message.conversation_id)
        else:
            if payload.conversation_id is not None:
                conversation = await session.get(Conversation, payload.conversation_id)
                if (
                    conversation is None
                    or conversation.rider_id != payload.rider_id
                    or conversation.status == "RESOLVED"
                ):
                    raise HTTPException(409, "Select an active conversation for this rider")
            else:
                conversation = await conversation_service.find_or_create(session, payload.rider_id)
            identifier = uuid4()
            inserted = await session.scalar(
                insert(Message)
                .values(
                    id=identifier,
                    conversation_id=conversation.id,
                    message_id=payload.message_id,
                    sender_type="RIDER",
                    content=payload.text,
                    is_internal=False,
                    received_at=payload.received_at,
                    processing_status="RECEIVED",
                    created_at=now,
                )
                .on_conflict_do_nothing(index_elements=[Message.message_id])
                .returning(Message.id)
            )
            if inserted is None:
                # Raising rolls back even a newly created conversation.
                raise ProcessingBusy
            message = await session.get(Message, identifier)
            trace_service.record(
                session,
                conversation.id,
                "message_in",
                "receive_message",
                input=payload.model_dump(mode="json"),
                at=now,
            )
        if message.agent_state is None:
            from app.core.clock import reference_time

            effective = reference_time(
                received_at=payload.received_at, interactive_demo=interactive_demo
            )
            message.agent_state = {"version": 1, "reference_time": effective.isoformat()}
            if interactive_demo:
                trace_service.record(
                    session,
                    conversation.id,
                    "decision",
                    "business_reference_clock",
                    output={
                        "received_at": payload.received_at,
                        "reference_time": effective,
                        "interactive_demo": True,
                    },
                )
        message.agent_attempts += 1
        message.next_processing_at = None
        token = uuid4()
        message.processing_status = "PROCESSING"
        message.processing_token = token
        message.processing_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        conversation.updated_at = now
        return Claim(
            message.id,
            conversation.id,
            payload.rider_id,
            token,
            conversation.handling_mode,
            conversation.control_version,
        )


async def deterministic_handler(claimed: Claim) -> str:
    # Future inference belongs here, outside all database transactions.
    return HUMAN_REPLY if claimed.handling_mode == "HUMAN" else AI_REPLY


async def complete(factory, claimed: Claim, reply: str) -> str:
    async with factory() as session, session.begin():
        await transaction_limits(session)
        await conversation_service.lock_rider(session, claimed.rider_id)
        message = await session.scalar(
            select(Message).where(Message.id == claimed.message_id).with_for_update()
        )
        if message.processing_status == "COMPLETED" and message.webhook_reply is not None:
            return message.webhook_reply
        if message.processing_token != claimed.token or message.processing_status != "PROCESSING":
            raise ProcessingBusy
        conversation = await session.scalar(
            select(Conversation).where(Conversation.id == claimed.conversation_id).with_for_update()
        )
        now = datetime.now(UTC)
        # Recheck current handling mode at completion; never simulate a human reply.
        if (
            conversation.handling_mode == "HUMAN"
            or conversation.control_version != claimed.control_version
            or conversation.status == "RESOLVED"
        ):
            reply = HUMAN_REPLY
        else:
            if reply == HUMAN_REPLY:
                reply = AI_REPLY
            session.add(
                Message(
                    id=uuid4(),
                    conversation_id=conversation.id,
                    sender_type="AI",
                    content=reply,
                    is_internal=False,
                    created_at=now,
                )
            )
        message.next_processing_at = None
        message.webhook_reply = reply
        message.processing_status = "COMPLETED"
        message.processing_token = None
        message.processing_expires_at = None
        conversation.updated_at = now
        trace_service.record(session, conversation.id, "reply", "send_reply", output=reply, at=now)
        return reply


async def failed(factory, claimed: Claim):
    async with factory() as session, session.begin():
        await transaction_limits(session)
        message = await session.scalar(
            select(Message).where(Message.id == claimed.message_id).with_for_update()
        )
        if message.processing_token == claimed.token and message.processing_status == "PROCESSING":
            message.processing_status = "FAILED"
            message.processing_token = None
            message.processing_expires_at = None
            trace_service.record(
                session,
                claimed.conversation_id,
                "error",
                "message_processing_failed",
                output={"retryable": True},
            )


PENDING_REPLY = (
    "Your message is saved. Verification is still pending; no payment outcome is confirmed."
)


async def run_handler(factory, claimed):
    from app.agent.graph import run_agent

    return await run_agent(factory, claimed)


def earlier_message(message, conversation_id, created_at, identifier):
    return and_(
        message.conversation_id == conversation_id,
        message.agent_state.is_not(None),
        message.processing_status.in_(("RECEIVED", "PROCESSING", "FAILED")),
        or_(
            message.created_at < created_at,
            and_(message.created_at == created_at, message.id < identifier),
        ),
    )


async def wait_for_turn(factory, claimed):
    while True:
        async with factory() as session:
            message = await session.get(Message, claimed.message_id)
            older = await session.scalar(
                select(
                    exists().where(
                        earlier_message(
                            Message, claimed.conversation_id, message.created_at, message.id
                        )
                    )
                )
            )
        if not older:
            return
        await asyncio.sleep(0.04)


async def execute(factory, claimed, *, worker=False):
    from app.realtime.publisher import Run, current_run

    current_run.set(Run(claimed.token, claimed.conversation_id, claimed.rider_id))
    seconds = (
        get_settings().agent_job_seconds if worker else get_settings().agent_foreground_seconds
    )
    try:
        async with asyncio.timeout(seconds):
            await wait_for_turn(factory, claimed)
            async with factory() as session:
                conversation = await session.get(Conversation, claimed.conversation_id)
                mode = conversation.handling_mode
                message = await session.get(Message, claimed.message_id)
                exhausted = message.agent_attempts > get_settings().agent_max_attempts
            if mode == "HUMAN":
                return HUMAN_REPLY
            if exhausted:
                from app.agent.tools import AgentTools

                return await AgentTools(factory, claimed).technical_escalation()
            return await run_handler(factory, claimed)
    except TimeoutError:
        raise AgentDeferred from None


async def defer(factory, claimed):
    async with factory() as session, session.begin():
        await transaction_limits(session)
        await conversation_service.lock_rider(session, claimed.rider_id)
        message = await session.scalar(
            select(Message).where(Message.id == claimed.message_id).with_for_update()
        )
        if message.processing_status == "COMPLETED":
            return message.webhook_reply
        if message.processing_token != claimed.token:
            raise ProcessingBusy
        message.processing_status = "RECEIVED"
        message.webhook_reply = PENDING_REPLY
        message.processing_token = None
        message.processing_expires_at = None
        from datetime import timedelta

        message.next_processing_at = datetime.now(UTC) + timedelta(
            seconds=min(30, 2 ** min(message.agent_attempts, 4))
        )
        trace_service.record(
            session,
            claimed.conversation_id,
            "decision",
            "agent_deferred",
            input={"message_id": message.id},
            output={"resume_at": message.next_processing_at},
        )
        return PENDING_REPLY


async def process(factory, payload: IncomingMessage, *, interactive_demo=False) -> str:
    try:
        async with asyncio.timeout(WEBHOOK_TIMEOUT_SECONDS):
            while True:
                try:
                    claimed = await claim(factory, payload, interactive_demo=interactive_demo)
                    if isinstance(claimed, str):
                        return claimed
                    try:
                        reply = await execute(factory, claimed)
                        return await complete(factory, claimed, reply)
                    except AgentDeferred:
                        return await defer(factory, claimed)
                    except (ProcessingBusy, OwnershipLost):
                        raise ProcessingBusy from None
                    except Exception:
                        await failed(factory, claimed)
                        raise
                except ProcessingBusy:
                    await asyncio.sleep(0.08)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail="Message processing; retry same message_id",
            headers={"Retry-After": "1"},
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Webhook processing failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Message processing unavailable; retry same message_id",
            headers={"Retry-After": "1"},
        ) from exc


async def resume_one(factory):
    """Drain a due message from PostgreSQL; duplicate workers cannot own the same claim."""
    now = datetime.now(UTC)
    older = aliased(Message)
    async with factory() as session:
        candidates = list(
            await session.scalars(
                select(Message)
                .where(
                    Message.agent_state["version"].as_integer() == 1,
                    Message.processing_status.in_(("RECEIVED", "PROCESSING", "FAILED")),
                    or_(Message.next_processing_at.is_(None), Message.next_processing_at <= now),
                    or_(
                        Message.processing_expires_at.is_(None),
                        Message.processing_expires_at <= now,
                    ),
                    ~exists().where(
                        earlier_message(
                            older, Message.conversation_id, Message.created_at, Message.id
                        )
                    ),
                )
                .order_by(Message.created_at, Message.id)
                .limit(10)
            )
        )
        payloads = []
        for message in candidates:
            conversation = await session.get(Conversation, message.conversation_id)
            payloads.append(
                IncomingMessage(
                    message_id=message.message_id,
                    rider_id=conversation.rider_id,
                    text=message.content,
                    received_at=message.received_at,
                )
            )
    for payload in payloads:
        try:
            claimed = await claim(factory, payload, from_worker=True)
            if isinstance(claimed, str):
                continue
            try:
                reply = await execute(factory, claimed, worker=True)
                await complete(factory, claimed, reply)
            except AgentDeferred:
                await defer(factory, claimed)
            except (ProcessingBusy, OwnershipLost):
                continue
            except Exception as exc:
                logger.warning("Durable agent job failed (%s)", type(exc).__name__)
                await defer(factory, claimed)
            return True
        except ProcessingBusy:
            continue
    return False
