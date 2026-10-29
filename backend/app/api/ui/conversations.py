from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.riders import Limit, Offset, Session, require_rider
from app.core.access import require_local_development
from app.repositories import conversations, disputes, messages
from app.schemas import Page
from app.schemas.conversations import ConversationResponse, DisputeResponse, MessageResponse
from app.services.conversation_service import message_response, summary

router = APIRouter(
    prefix="/ui", tags=["local rider simulator"], dependencies=[Depends(require_local_development)]
)


def paginated(items, total, limit, offset):
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def own_conversation(session, conversation_id, rider_id):
    row = await conversations.get(session, conversation_id, rider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row


@router.get("/riders/{rider_id}/conversations", response_model=Page[ConversationResponse])
async def rider_conversations(
    rider_id: str, session: Session, limit: Limit = 50, offset: Offset = 0
):
    await require_rider(session, rider_id)
    rows, total = await conversations.list_conversations(
        session, rider_id=rider_id, limit=limit, offset=offset
    )
    return paginated([summary(row) for row in rows], total, limit, offset)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def conversation(conversation_id: UUID, rider_id: str, session: Session):
    return summary(await own_conversation(session, conversation_id, rider_id))


@router.get("/conversations/{conversation_id}/messages", response_model=Page[MessageResponse])
async def conversation_messages(
    conversation_id: UUID,
    rider_id: str,
    session: Session,
    limit: Limit = 50,
    offset: Offset = 0,
):
    await own_conversation(session, conversation_id, rider_id)
    rows, total = await messages.history(session, conversation_id, limit=limit, offset=offset)
    return paginated([message_response(row) for row in rows], total, limit, offset)


@router.get("/conversations/{conversation_id}/disputes", response_model=Page[DisputeResponse])
async def conversation_disputes(
    conversation_id: UUID,
    rider_id: str,
    session: Session,
    limit: Limit = 50,
    offset: Offset = 0,
):
    await own_conversation(session, conversation_id, rider_id)
    rows, total = await disputes.for_conversation(
        session, conversation_id, limit=limit, offset=offset
    )
    return paginated(rows, total, limit, offset)
