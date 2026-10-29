from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message
from app.repositories.pagination import page


async def webhook(session: AsyncSession, external_id: str):
    return (
        await session.execute(
            select(Message, Conversation.rider_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Message.message_id == external_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()


async def history(
    session: AsyncSession, conversation_id: UUID, *, internal=False, limit=50, offset=0
):
    statement = select(Message).where(Message.conversation_id == conversation_id)
    if not internal:
        statement = statement.where(Message.is_internal.is_(False))
    rows, total = await page(
        session, statement.order_by(Message.created_at, Message.id), limit=limit, offset=offset
    )
    return [row[0] for row in rows], total
