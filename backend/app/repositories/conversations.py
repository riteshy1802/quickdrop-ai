from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Dispute, Message, PaymentIntent
from app.repositories.pagination import page


def summaries():
    last_message = (
        select(Message.content)
        .where(Message.conversation_id == Conversation.id, Message.is_internal.is_(False))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )
    title = (
        select(Message.content)
        .where(Message.conversation_id == Conversation.id, Message.sender_type == "RIDER")
        .order_by(Message.created_at, Message.id)
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )
    verification_required = (
        exists()
        .where(
            Dispute.conversation_id == Conversation.id,
            PaymentIntent.dispute_id == Dispute.id,
            PaymentIntent.status == "NEEDS_REVIEW",
        )
        .correlate(Conversation)
    )
    return select(
        Conversation,
        last_message.label("last_message"),
        title.label("title"),
        verification_required.label("verification_required"),
    )


async def active(session: AsyncSession, rider_id: str):
    return await session.scalar(
        select(Conversation)
        .where(Conversation.rider_id == rider_id, Conversation.status != "RESOLVED")
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(1)
    )


async def get(session: AsyncSession, conversation_id: UUID, rider_id: str | None = None):
    statement = summaries().where(Conversation.id == conversation_id)
    if rider_id is not None:
        statement = statement.where(Conversation.rider_id == rider_id)
    return (await session.execute(statement)).one_or_none()


async def list_conversations(
    session: AsyncSession, *, rider_id=None, handling_mode=None, status=None, limit=50, offset=0
):
    statement = summaries()
    for column, value in (
        (Conversation.rider_id, rider_id),
        (Conversation.handling_mode, handling_mode),
        (Conversation.status, status),
    ):
        if value is not None:
            statement = statement.where(column == value)
    return await page(
        session,
        statement.order_by(Conversation.updated_at.desc(), Conversation.id.desc()),
        limit=limit,
        offset=offset,
    )
