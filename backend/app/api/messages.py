from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_session_factory
from app.schemas.messages import IncomingMessage, MessageReply
from app.services.message_service import process

router = APIRouter(tags=["messaging vendor"])


@router.post("/messages", response_model=MessageReply)
async def post_message(
    payload: IncomingMessage,
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
):
    return {"reply": await process(factory, payload)}
