from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_session_factory
from app.schemas.messages import IncomingMessage, MessageReply
from app.services.message_service import process

router = APIRouter(tags=["messaging vendor"])


@router.post("/messages", response_model=MessageReply)
async def post_message(
    payload: IncomingMessage,
    request: Request,
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
):
    if payload.conversation_id is not None:
        from app.core.demo import require_demo
        from app.services.auth_service import check_origin

        check_origin(request)
        require_demo(request, payload.rider_id)
    return {
        "reply": await process(
            factory, payload, interactive_demo=payload.conversation_id is not None
        )
    }
