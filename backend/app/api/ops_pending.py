from fastapi import APIRouter, Depends

from app.api.riders import Session
from app.core.access import require_local_development
from app.repositories import ops_queue
from app.schemas.ops import PendingItem

router = APIRouter(tags=["assignment ops"], dependencies=[Depends(require_local_development)])


def pending_response(row):
    queue, dispute = row
    return {
        "id": queue.id,
        "rider_id": dispute.rider_id,
        "type": queue.type,
        "amount": queue.amount if queue.type == "approval" else None,
        "reason": queue.reason,
        "created_at": queue.created_at,
    }


@router.get("/ops/pending", response_model=list[PendingItem])
async def get_pending(session: Session):
    return [pending_response(row) for row in await ops_queue.pending(session)]
