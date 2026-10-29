from fastapi import APIRouter

from app.api.riders import Session, require_rider
from app.schemas.traces import TraceEvent
from app.services import trace_service

router = APIRouter(tags=["assignment audit"])


@router.get("/trace/{rider_id}", response_model=list[TraceEvent])
async def get_trace(rider_id: str, session: Session):
    await require_rider(session, rider_id)
    return [
        trace_service.event(row[0])
        for row in await trace_service.retrieve(session, rider_id=rider_id)
    ]
