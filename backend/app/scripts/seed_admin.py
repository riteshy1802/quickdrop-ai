"""Explicit, idempotent Ops administrator seed; never runs during app startup."""

import asyncio

from app.core.config import get_settings
from app.core.database import get_engine, get_session_factory
from app.services.auth_service import seed_admin


async def main():
    settings = get_settings()
    if not settings.ops_admin_email or not settings.ops_admin_password:
        raise ValueError("Set OPS_ADMIN_EMAIL and OPS_ADMIN_PASSWORD")
    try:
        async with get_session_factory()() as session, session.begin():
            _, created = await seed_admin(
                session, settings.ops_admin_email, settings.ops_admin_password.get_secret_value()
            )
        print(
            "Ops administrator created"
            if created
            else "Ops administrator already exists; unchanged"
        )
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
