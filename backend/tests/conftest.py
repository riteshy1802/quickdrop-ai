"""All integration tests use a newly created disposable database, never quickdrop."""

import asyncio
import os
import subprocess
import sys
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import BACKEND_DIR, get_settings
from app.scripts.seed import seed_data


def migrate(url, *args):
    env = os.environ.copy()
    env["DATABASE_URL"] = url.render_as_string(hide_password=False)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture(scope="session")
def database_url():
    configured = get_settings().sqlalchemy_url
    name = "quickdrop_test_" + uuid4().hex
    admin_url = configured.set(database="postgres")

    async def manage(action):
        conn = await asyncpg.connect(
            host=admin_url.host,
            port=admin_url.port or 5432,
            user=admin_url.username,
            password=admin_url.password,
            database="postgres",
        )
        try:
            assert name.startswith("quickdrop_test_") and len(name) == 47
            await conn.execute(
                f'CREATE DATABASE "{name}"'
                if action == "create"
                else f'DROP DATABASE "{name}" WITH (FORCE)'
            )
        finally:
            await conn.close()

    asyncio.run(manage("create"))
    url = configured.set(database=name)
    try:
        migrate(url, "upgrade", "head")
        yield url
        # Exercise rollback only in this disposable test database.
        migrate(url, "downgrade", "base")
        migrate(url, "upgrade", "head")
        migrate(url, "check")
    finally:
        asyncio.run(manage("drop"))


@pytest_asyncio.fixture
async def connection(database_url):
    engine = create_async_engine(database_url, poolclass=NullPool, hide_parameters=True)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def session(connection):
    async with AsyncSession(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    ) as session:
        yield session


@pytest_asyncio.fixture
async def seeded(session):
    async with session.begin():
        counts = await seed_data(session)
    return counts


@pytest_asyncio.fixture(autouse=True)
async def isolate_realtime_publishing(monkeypatch):
    from unittest.mock import AsyncMock

    from app.realtime import publisher

    monkeypatch.setattr(publisher, "publish", AsyncMock())
    yield
    await publisher.drain()
