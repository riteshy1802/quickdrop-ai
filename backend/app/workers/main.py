"""Run with uv run python -m app.workers.main. No schema changes at startup."""

import asyncio
import logging
import signal

from app.core.config import get_settings
from app.core.database import get_engine, get_session_factory
from app.integrations.payswift import get_payswift_client
from app.services.message_service import resume_one
from app.services.payment_worker import process_one

logger = logging.getLogger(__name__)


async def run():
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    client = get_payswift_client()
    settings = get_settings()
    try:
        while not stop.is_set():
            phase = "Agent"
            try:
                agent_work = await resume_one(get_session_factory())
                phase = "Payment"
                payment_work = await process_one(get_session_factory(), client)
                if agent_work or payment_work:
                    continue
            except Exception as exc:
                # Exception text can contain SQL values or URLs. Log only its class.
                if isinstance(exc, ConnectionRefusedError):
                    logger.warning(
                        "%s worker database connection refused; run make infra-up "
                        "and check POSTGRES_HOST/POSTGRES_PORT",
                        phase,
                    )
                else:
                    logger.warning("%s worker iteration failed (%s)", phase, type(exc).__name__)
            try:
                await asyncio.wait_for(stop.wait(), settings.payment_poll_seconds)
            except TimeoutError:
                pass
    finally:
        from app.realtime.publisher import drain

        await drain()
        await client.aclose()
        get_payswift_client.cache_clear()
        await get_engine().dispose()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
