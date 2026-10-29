"""Active means not RESOLVED. Most recently updated active thread wins."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Rider
from app.repositories import conversations, messages
from app.services.trace_service import safe_json


async def lock_rider(session: AsyncSession, rider_id: str):
    # All conversation creators must take this row lock to avoid first-message races.
    return await session.scalar(select(Rider).where(Rider.rider_id == rider_id).with_for_update())


async def find_or_create(session: AsyncSession, rider_id: str):
    if await lock_rider(session, rider_id) is None:
        raise ValueError("Rider not found")
    conversation = await conversations.active(session, rider_id)
    if conversation is None:
        now = datetime.now(UTC)
        conversation = Conversation(
            id=uuid4(),
            rider_id=rider_id,
            status="OPEN",
            handling_mode="AI",
            context={},
            created_at=now,
            updated_at=now,
        )
        session.add(conversation)
        await session.flush()
    return conversation


async def load_history(session: AsyncSession, conversation_id, *, limit=50, offset=0):
    return await messages.history(session, conversation_id, limit=limit, offset=offset)


def set_context(conversation: Conversation, context: dict):
    # Never store credentials or private reasoning in conversation context.
    conversation.context = safe_json(context)
    conversation.updated_at = datetime.now(UTC)


def summary(row):
    conversation, last_message, title = row
    status = conversation.status
    if status == "AWAITING_INFORMATION":
        status = "OPEN"
    elif status == "ESCALATED":
        status = "HUMAN_HANDLING" if conversation.handling_mode == "HUMAN" else "AWAITING_APPROVAL"
    return {
        "id": conversation.id,
        "rider_id": conversation.rider_id,
        "title": (title or "Conversation")[:80],
        "status": status,
        "source_status": conversation.status,
        "handler": "OPS" if conversation.handling_mode == "HUMAN" else "AI",
        "handling_mode": conversation.handling_mode,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "last_message": last_message or "",
        "scenario": None,
    }


def message_response(message):
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender": message.sender_type,
        "text": message.content,
        "created_at": message.created_at,
        "received_at": message.received_at,
        "visibility": "INTERNAL" if message.is_internal else "RIDER",
    }


def get_context(conversation: Conversation) -> dict:
    return safe_json(conversation.context)


def set_lifecycle(conversation: Conversation, *, status: str, handling_mode: str):
    if status not in {
        "OPEN",
        "AWAITING_INFORMATION",
        "AWAITING_APPROVAL",
        "ESCALATED",
        "HUMAN_HANDLING",
        "PAYMENT_PENDING",
        "RESOLVED",
    }:
        raise ValueError("Unsupported conversation status")
    if handling_mode not in {"AI", "HUMAN"}:
        raise ValueError("Unsupported handling mode")
    if conversation.status == "RESOLVED" and status != "RESOLVED":
        raise ValueError("Resolved conversations cannot be reopened")
    conversation.status = status
    conversation.handling_mode = handling_mode
    conversation.updated_at = datetime.now(UTC)
