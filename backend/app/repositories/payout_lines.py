from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PayoutLine
from app.schemas.payout import PayoutLineType


def _filters(rider_id, date_from, date_to, line_type, trip_ids):
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from must be on or before date_to")
    filters = [PayoutLine.rider_id == rider_id]
    if date_from:
        filters.append(PayoutLine.payout_date >= date_from)
    if date_to:
        filters.append(PayoutLine.payout_date <= date_to)
    if line_type:
        filters.append(PayoutLine.line_type == line_type)
    if trip_ids is not None:
        filters.append(PayoutLine.trip_id.in_(trip_ids))
    return filters


async def list_for_rider(
    session: AsyncSession,
    rider_id: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    line_type: PayoutLineType | None = None,
    trip_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PayoutLine], int]:
    filters = _filters(rider_id, date_from, date_to, line_type, [trip_id] if trip_id else None)
    total = await session.scalar(select(func.count()).select_from(PayoutLine).where(*filters))
    rows = await session.scalars(
        select(PayoutLine)
        .where(*filters)
        .order_by(
            PayoutLine.payout_date,
            PayoutLine.line_id,
        )
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total or 0


async def find_by_trip_id(session: AsyncSession, trip_id: str) -> list[PayoutLine]:
    return list(
        await session.scalars(
            select(PayoutLine)
            .where(
                PayoutLine.trip_id == trip_id,
            )
            .order_by(PayoutLine.payout_date, PayoutLine.line_id)
        )
    )


async def find_for_claim(
    session: AsyncSession,
    rider_id: str,
    *,
    trip_ids: Sequence[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    line_type: PayoutLineType | None = None,
) -> list[PayoutLine]:
    """Retrieve source history in an explicit claim scope; supplied filters intersect.

    Date-only scopes include tripless daily incentives. An explicit trip scope
    returns only those trips; no expected earnings or eligibility is inferred.
    """
    if trip_ids is None and date_from is None and date_to is None:
        raise ValueError("Provide trip IDs or a claim date range")
    filters = _filters(rider_id, date_from, date_to, line_type, trip_ids)
    return list(
        await session.scalars(
            select(PayoutLine)
            .where(*filters)
            .order_by(
                PayoutLine.payout_date,
                PayoutLine.line_id,
            )
        )
    )
