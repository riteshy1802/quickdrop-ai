from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories import payout_lines, riders, trips
from app.schemas import Page
from app.schemas.payout import PayoutLineResponse, PayoutLineType
from app.schemas.rider import RiderResponse
from app.schemas.trip import TripResponse, TripStatus

router = APIRouter(prefix="/ui/riders", tags=["development data"])
Session = Annotated[AsyncSession, Depends(get_db_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


async def require_rider(session: AsyncSession, rider_id: str):
    rider = await riders.get_by_id(session, rider_id)
    if rider is None:
        raise HTTPException(status_code=404, detail="Rider not found")
    return rider


def validate_dates(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    if date_to == date.max:
        raise HTTPException(status_code=422, detail="date_to must be earlier than 9999-12-31")


@router.get("", response_model=Page[RiderResponse])
async def list_riders(session: Session, limit: Limit = 50, offset: Offset = 0):
    items, total = await riders.list_riders(session, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{rider_id}", response_model=RiderResponse)
async def get_rider(rider_id: str, session: Session):
    return await require_rider(session, rider_id)


@router.get("/{rider_id}/trips", response_model=Page[TripResponse])
async def list_trips(
    rider_id: str,
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    status: TripStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    validate_dates(date_from, date_to)
    await require_rider(session, rider_id)
    items, total = await trips.list_for_rider(
        session,
        rider_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{rider_id}/payout-lines", response_model=Page[PayoutLineResponse])
async def list_payouts(
    rider_id: str,
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    line_type: PayoutLineType | None = None,
    trip_id: str | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    validate_dates(date_from, date_to)
    await require_rider(session, rider_id)
    items, total = await payout_lines.list_for_rider(
        session,
        rider_id,
        date_from=date_from,
        date_to=date_to,
        line_type=line_type,
        trip_id=trip_id,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
