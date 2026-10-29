"""Best-effort transient events. Delivery failure never invalidates committed business work."""

import asyncio
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.realtime.events import EventData, LiveEvent

logger = logging.getLogger(__name__)
_tasks = set()


@dataclass
class Run:
    run_id: UUID
    conversation_id: UUID
    rider_id: str
    sequence: int = 0


current_run: ContextVar[Run | None] = ContextVar("live_run", default=None)


def make_event(kind, conversation_id, rider_id, **data):
    run = current_run.get()
    kwargs = {}
    if run and run.conversation_id == conversation_id:
        run.sequence += 1
        kwargs = {"run_id": run.run_id, "sequence": run.sequence}
    return LiveEvent(
        event_type=kind,
        conversation_id=conversation_id,
        rider_id=rider_id,
        data=EventData(**data),
        **kwargs,
    )


async def publish(event: LiveEvent, *, internal=False):
    try:
        async with asyncio.timeout(0.4):
            async with Redis.from_url(
                get_settings().redis_url.get_secret_value(),
                socket_connect_timeout=0.2,
                socket_timeout=0.3,
                decode_responses=True,
            ) as redis:
                channels = ["quickdrop:ops:events"]
                if not internal:
                    channels.append(f"quickdrop:conversation:{event.conversation_id}")
                for channel in channels:
                    await redis.publish(channel, event.model_dump_json(exclude_none=True))
    except (OSError, TimeoutError, RedisError, ValueError):
        logger.warning("Realtime delivery unavailable")


async def progress(claimed, status, *, kind="agent.status"):
    await publish(
        make_event(
            kind,
            claimed.conversation_id,
            claimed.rider_id,
            status=status,
            control_version=claimed.control_version,
        )
    )


def schedule(events):
    if not events:
        return

    async def deliver():
        for event, internal in events:
            await publish(event, internal=internal)
            if event.event_type == "agent.message.delta":
                await asyncio.sleep(0.04)

    try:
        task = asyncio.get_running_loop().create_task(deliver())
    except RuntimeError:
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def drain():
    if _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)
