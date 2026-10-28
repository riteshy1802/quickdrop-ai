from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Trip
from app.schemas.trip import TripStatus

IST = ZoneInfo("Asia/Kolkata")


def ist_date_range(
    date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    """Inclusive IST calendar dates become a half-open UTC timestamp range."""
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from must be on or before date_to")
    start = datetime.combine(date_from, time.min, IST).astimezone(UTC) if date_from else None
    end = (
        datetime.combine(date_to + timedelta(days=1), time.min, IST).astimezone(UTC)
        if date_to
        else None
    )
    return start, end


async def get_by_id(session: AsyncSession, trip_id: str) -> Trip | None:
    return await session.get(Trip, trip_id)


async def list_for_rider(
    session: AsyncSession,
    rider_id: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    status: TripStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Trip], int]:
    start, end = ist_date_range(date_from, date_to)
    filters = [Trip.rider_id == rider_id]
    if start:
        filters.append(Trip.started_at >= start)
    if end:
        filters.append(Trip.started_at < end)
    if status:
        filters.append(Trip.status == status)
    total = await session.scalar(select(func.count()).select_from(Trip).where(*filters))
    items = await session.scalars(
        select(Trip)
        .where(*filters)
        .order_by(
            Trip.started_at,
            Trip.trip_id,
        )
        .limit(limit)
        .offset(offset)
    )
    return list(items), total or 0


async def count_completed_on_date(session: AsyncSession, rider_id: str, day: date) -> int:
    start, end = ist_date_range(day, day)
    return (
        await session.scalar(
            select(func.count())
            .select_from(Trip)
            .where(
                Trip.rider_id == rider_id,
                Trip.status == "completed",
                Trip.started_at >= start,
                Trip.started_at < end,
            )
        )
        or 0
    )
