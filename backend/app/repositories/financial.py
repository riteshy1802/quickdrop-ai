"""Batched, read-only source retrieval. No policy calculations or payment mutations."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Dispute, PayoutLine, Trip
from app.repositories.trips import ist_date_range


def _date_conditions(days: Sequence[date]):
    conditions = []
    for day in sorted(set(days)):
        start, end = ist_date_range(day, day)
        conditions.append(and_(Trip.started_at >= start, Trip.started_at < end))
    return conditions


async def trips_for_scope(
    session: AsyncSession,
    rider_id: str,
    trip_ids: Sequence[str],
    days: Sequence[date],
) -> list[Trip]:
    filters = []
    if trip_ids:
        # Include explicitly requested foreign-owner trips so eligibility can reject them.
        filters.append(Trip.trip_id.in_(trip_ids))
    dates = _date_conditions(days)
    if dates:
        filters.append(and_(Trip.rider_id == rider_id, or_(*dates)))
    if not filters:
        return []
    return list(await session.scalars(select(Trip).where(or_(*filters)).order_by(Trip.trip_id)))


async def payouts_for_scope(
    session: AsyncSession,
    rider_id: str,
    trip_ids: Sequence[str],
    days: Sequence[date],
) -> list[PayoutLine]:
    filters = []
    if trip_ids:
        # Retrieve all dates for scoped trips: wrong-date entries must not look like missing pay.
        filters.append(PayoutLine.trip_id.in_(trip_ids))
    if days:
        filters.append(PayoutLine.payout_date.in_(days))
    if not filters:
        return []
    return list(
        await session.scalars(
            select(PayoutLine)
            .where(
                PayoutLine.rider_id == rider_id,
                or_(*filters),
            )
            .order_by(PayoutLine.payout_date, PayoutLine.line_id)
        )
    )


async def prior_claims(session: AsyncSession, rider_id: str) -> list[Dispute]:
    return list(
        await session.scalars(
            select(Dispute)
            .where(
                Dispute.rider_id == rider_id,
            )
            .options(selectinload(Dispute.items), selectinload(Dispute.payment_intents))
            .order_by(Dispute.id)
        )
    )
