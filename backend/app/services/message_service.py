"""Durable webhook claim, processing outside transactions, atomic completion."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

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
        rider_id != payload.rider_id
        or message.content != payload.text
        or message.received_at != payload.received_at
    ):
        raise HTTPException(status_code=409, detail="Message ID reused with conflicting payload")


async def claim(factory, payload: IncomingMessage) -> Claim | str:
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
                message.processing_status == "PROCESSING"
                and message.processing_expires_at
                and message.processing_expires_at > now
            ):
                raise ProcessingBusy
            # Expired/failed/received work is recoverable. No duplicate input trace.
            conversation = await session.get(Conversation, message.conversation_id)
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
        token = uuid4()
        message.processing_status = "PROCESSING"
        message.processing_token = token
        message.processing_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        conversation.updated_at = now
        return Claim(
            message.id, conversation.id, payload.rider_id, token, conversation.handling_mode
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
        if conversation.handling_mode == "HUMAN":
            reply = HUMAN_REPLY
        else:
            if claimed.handling_mode == "HUMAN":
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


async def process(factory, payload: IncomingMessage) -> str:
    try:
        async with asyncio.timeout(WEBHOOK_TIMEOUT_SECONDS):
            while True:
                try:
                    claimed = await claim(factory, payload)
                    if isinstance(claimed, str):
                        return claimed
                    try:
                        reply = await deterministic_handler(claimed)
                        return await complete(factory, claimed, reply)
                    except ProcessingBusy:
                        raise
                    except Exception:
                        await failed(factory, claimed)
                        raise
                except ProcessingBusy:
                    # No transaction or connection is held while another owner completes.
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
