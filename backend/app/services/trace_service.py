"""Reusable audit writer. Caller commits traces together with related state."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentTrace, Conversation
from app.models.agent_trace import redact_trace_payload
from app.repositories.pagination import page
from app.schemas.traces import TraceType


def safe_json(value):
    # Decimal is serialized as a string, without binary floating-point loss.
    encoded = redact_trace_payload(jsonable_encoder(value, custom_encoder={Decimal: str}))
    # Reject non-JSON floats before a database write.
    json.dumps(encoded, allow_nan=False)
    return encoded


def record(
    session: AsyncSession,
    conversation_id: UUID,
    event_type: TraceType,
    name: str,
    *,
    input=None,
    output=None,
    at: datetime | None = None,
) -> AgentTrace:
    if event_type not in {"message_in", "tool_call", "decision", "reply", "error"}:
        raise ValueError("Unsupported trace type")
    if input is not None and not isinstance(input, dict):
        raise ValueError("Trace input must be an object or null")
    timestamp = at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Trace timestamp must be timezone-aware")
    trace = AgentTrace(
        id=uuid4(),
        conversation_id=conversation_id,
        type=event_type,
        name=name,
        input=safe_json(input),
        output=safe_json(output),
        created_at=timestamp,
    )
    session.add(trace)
    return trace


def event(trace: AgentTrace):
    return {
        "at": trace.created_at,
        "type": trace.type,
        "name": trace.name,
        "input": safe_json(trace.input),
        "output": safe_json(trace.output),
    }


async def retrieve(
    session: AsyncSession,
    *,
    rider_id=None,
    conversation_id=None,
    event_type=None,
    limit: int | None = None,
    offset=0,
):
    statement = select(AgentTrace, Conversation.rider_id).join(
        Conversation, Conversation.id == AgentTrace.conversation_id
    )
    for column, value in (
        (Conversation.rider_id, rider_id),
        (AgentTrace.conversation_id, conversation_id),
        (AgentTrace.type, event_type),
    ):
        if value is not None:
            statement = statement.where(column == value)
    statement = statement.order_by(AgentTrace.created_at, AgentTrace.id)
    if limit is None:
        return (await session.execute(statement)).all()
    return await page(session, statement, limit=limit, offset=offset)
