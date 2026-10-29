from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Dispute
from app.repositories.pagination import page


async def for_conversation(session: AsyncSession, conversation_id: UUID, *, limit=50, offset=0):
    rows, total = await page(
        session,
        select(Dispute)
        .where(Dispute.conversation_id == conversation_id)
        .options(selectinload(Dispute.items))
        .order_by(Dispute.created_at, Dispute.id),
        limit=limit,
        offset=offset,
    )
    return [row[0] for row in rows], total
