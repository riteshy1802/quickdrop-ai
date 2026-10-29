from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dispute, OpsQueue
from app.repositories.pagination import page


def statement():
    return select(OpsQueue, Dispute).join(Dispute, Dispute.id == OpsQueue.dispute_id)


async def pending(session: AsyncSession):
    return (
        await session.execute(
            statement()
            .where(OpsQueue.status.in_(("PENDING", "IN_REVIEW")), OpsQueue.resolved_at.is_(None))
            .order_by(OpsQueue.created_at, OpsQueue.id)
        )
    ).all()


async def list_cases(session: AsyncSession, *, rider_id=None, status=None, limit=50, offset=0):
    query = statement()
    if rider_id is not None:
        query = query.where(Dispute.rider_id == rider_id)
    if status is not None:
        query = query.where(OpsQueue.status == status)
    return await page(
        session, query.order_by(OpsQueue.created_at, OpsQueue.id), limit=limit, offset=offset
    )


async def get_case(session: AsyncSession, identifier):
    return (await session.execute(statement().where(OpsQueue.id == identifier))).one_or_none()
