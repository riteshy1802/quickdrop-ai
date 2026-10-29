from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Conversation, Dispute, DisputeItem
from app.repositories.pagination import page


async def visible_scope(session, conversation_id):
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        return select(Dispute.id).where(False)
    ids = [UUID(value) for value in conversation.context.get("agent", {}).get("dispute_ids", [])]
    extraction = conversation.context.get("agent", {}).get("extraction", {})
    trip_ids = [
        value.upper()
        for claim in extraction.get("claims", [])
        for value in claim.get("trip_ids", [])
    ]
    return select(Dispute.id).where(
        Dispute.rider_id == conversation.rider_id,
        or_(
            Dispute.conversation_id == conversation_id,
            Dispute.id.in_(ids),
            Dispute.id.in_(
                select(DisputeItem.dispute_id).where(
                    DisputeItem.source_type == "trip", DisputeItem.source_id.in_(trip_ids)
                )
            ),
        ),
    )


async def for_conversation(session: AsyncSession, conversation_id: UUID, *, limit=50, offset=0):
    rows, total = await page(
        session,
        select(Dispute)
        .where(Dispute.id.in_(await visible_scope(session, conversation_id)))
        .options(selectinload(Dispute.items))
        .order_by(Dispute.created_at, Dispute.id),
        limit=limit,
        offset=offset,
    )
    return [row[0] for row in rows], total
