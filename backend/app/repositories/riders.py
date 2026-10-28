from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Rider


async def get_by_id(session: AsyncSession, rider_id: str) -> Rider | None:
    return await session.get(Rider, rider_id)


async def exists(session: AsyncSession, rider_id: str) -> bool:
    return bool(
        await session.scalar(select(select(Rider).where(Rider.rider_id == rider_id).exists()))
    )


async def list_riders(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Rider], int]:
    total = await session.scalar(select(func.count()).select_from(Rider))
    items = await session.scalars(
        select(Rider).order_by(Rider.rider_id).limit(limit).offset(offset)
    )
    return list(items), total or 0
