from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def page(session: AsyncSession, statement, *, limit: int, offset: int):
    total = await session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    rows = (await session.execute(statement.limit(limit).offset(offset))).all()
    return rows, total or 0
