"""Authorized subscriptions with transient Redis delivery and PostgreSQL recovery."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import select

from app.api.riders import Session
from app.core.database import get_session_factory
from app.core.demo import require_demo
from app.models import Conversation, OpsSession
from app.realtime.events import LiveEvent
from app.realtime.subscriber import subscribe
from app.services.auth_service import COOKIE, Operator, digest

router = APIRouter(tags=["Live events"])


async def stream(request, channel, *, session_valid=None):
    yield "retry: 2000\n\n"
    try:
        async with subscribe(channel) as pubsub:
            yield "event: ready\ndata: {}\n\n"
            while not await request.is_disconnected():
                if session_valid and not await session_valid():
                    yield "event: session.expired\ndata: {}\n\n"
                    return
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if message is None:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(0.01)
                    continue
                try:
                    envelope = LiveEvent.model_validate_json(message["data"])
                except (ValidationError, KeyError, TypeError):
                    continue
                yield envelope.sse()
    except (RedisError, OSError, TimeoutError):
        yield "event: unavailable\ndata: {}\n\n"


def response(generator):
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/ui/conversations/{identifier}/events")
async def conversation_events(identifier: UUID, rider_id: str, request: Request, session: Session):
    require_demo(request, rider_id)
    owner = await session.scalar(select(Conversation.rider_id).where(Conversation.id == identifier))
    if owner != rider_id:
        raise HTTPException(404, "Conversation not found")
    # Release the read transaction/connection before opening a long-lived stream.
    await session.rollback()
    return response(
        stream(
            request,
            f"quickdrop:conversation:{identifier}",
            session_valid=lambda: demo_valid(request, rider_id),
        )
    )


async def demo_valid(request, rider_id):
    try:
        require_demo(request, rider_id)
        return True
    except HTTPException:
        return False


@router.get("/ui/ops/events")
async def ops_events(request: Request, operator: Operator, factory=Depends(get_session_factory)):
    from datetime import UTC, datetime

    async def valid():
        async with factory() as session:
            return bool(
                await session.scalar(
                    select(OpsSession.digest).where(
                        OpsSession.digest == digest(request.cookies[COOKIE]),
                        OpsSession.expires_at > datetime.now(UTC),
                    )
                )
            )

    return response(stream(request, "quickdrop:ops:events", session_valid=valid))
