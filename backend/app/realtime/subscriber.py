from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.core.config import get_settings


@asynccontextmanager
async def subscribe(channel):
    async with Redis.from_url(
        get_settings().redis_url.get_secret_value(),
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=30,
    ) as redis:
        async with redis.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            try:
                yield pubsub
            finally:
                await pubsub.unsubscribe(channel)
