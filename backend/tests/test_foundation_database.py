import asyncio
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import database
from app.core.config import BACKEND_DIR
from app.core.database import get_db_session
from app.main import create_app
from app.models import PayoutLine, Rider, Trip
from app.repositories import payout_lines, riders, trips
from app.scripts.seed import DEFAULT_DATA_DIR, SeedError, read_datasets, seed_data

pytestmark = pytest.mark.database

# The two reference mappings explicitly approved for these source exports.
ALIASES = {"R7": "R007", "r19": "R019"}


@pytest_asyncio.fixture
async def client(session, seeded):
    app = create_app()

    async def dependency():
        yield session

    app.dependency_overrides[get_db_session] = dependency
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        yield client


async def test_seed_exact_values_idempotency_and_no_overwrites(session, seeded):
    datasets = read_datasets()
    for row in datasets["trips"]:
        row["rider_id"] = ALIASES.get(row["rider_id"], row["rider_id"])
    expected_first = {
        name: {"inserted": len(rows), "skipped": 0} for name, rows in datasets.items()
    }
    expected_first["trips"] = {"inserted": 3304, "skipped": 10, "remapped_rider_references": 64}
    assert seeded == expected_first
    for model in (Rider, Trip, PayoutLine):
        source = {
            row[next(iter(model.__table__.primary_key)).name]: row
            for row in datasets[model.__tablename__]
        }
        key = next(iter(model.__table__.primary_key))
        imported = (
            await session.execute(select(model.__table__).where(key.in_(source)))
        ).mappings()
        assert {row[key.name]: dict(row) for row in imported} == source
    assert (
        await session.scalar(
            select(PayoutLine.amount).where(
                PayoutLine.line_id == "PL000006",
            )
        )
    ) == Decimal("-10")
    assert (await session.get(PayoutLine, "PL000023")).trip_id is None
    original = await session.get(Rider, "R001")
    original.name = "Existing operator-edited name"
    await session.commit()
    second = await seed_data(session)
    expected_second = {
        name: {"inserted": 0, "skipped": len(rows)} for name, rows in datasets.items()
    }
    expected_second["trips"]["remapped_rider_references"] = 64
    assert second == expected_second
    await session.refresh(original)
    assert original.name == "Existing operator-edited name"


async def test_repositories_and_ist_boundary(session, seeded):
    assert (await riders.get_by_id(session, "R001")).rider_id == "R001"
    assert await riders.exists(session, "R001")
    assert not await riders.exists(session, "not-a-rider")
    page, total = await riders.list_riders(session, limit=2, offset=1)
    assert [r.rider_id for r in page] == ["R002", "R003"] and total == 40
    assert (await trips.get_by_id(session, "T702770")).distance_km == Decimal("10.7")
    assert await trips.get_by_id(session, "missing") is None
    day = date(2026, 9, 22)
    start = datetime(2026, 9, 21, 18, 30, tzinfo=UTC)
    assert trips.ist_date_range(day, day) == (start, start + timedelta(days=1))
    rider = "B" + uuid4().hex[:20]
    session.add(Rider(rider_id=rider, name="Boundary rider", city="Test", joined_on=day))
    await session.flush()
    for index, timestamp in enumerate(
        [
            start - timedelta(microseconds=1),
            start,
            start + timedelta(days=1, microseconds=-1),
            start + timedelta(days=1),
        ]
    ):
        session.add(
            Trip(
                trip_id=f"{rider}-{index}",
                rider_id=rider,
                started_at=timestamp,
                status="completed",
                distance_km=Decimal("2.123456789"),
                surge_multiplier=Decimal("1.25"),
            )
        )
    await session.flush()
    records, count = await trips.list_for_rider(
        session,
        rider,
        date_from=day,
        date_to=day,
        status="completed",
    )
    assert count == 2 and len(records) == 2
    assert records[0].distance_km == Decimal("2.123456789")
    assert await trips.count_completed_on_date(session, rider, day) == 2
    _, count = await trips.list_for_rider(session, rider, status="cancelled_by_rider")
    assert count == 0
    lines = await payout_lines.find_by_trip_id(session, "T842792")
    assert len(lines) == 1 and lines[0].amount == -10
    history = await payout_lines.find_for_claim(
        session,
        "R001",
        date_from=date(2026, 9, 13),
        date_to=date(2026, 9, 13),
    )
    assert any(line.trip_id is None for line in history)
    history = await payout_lines.find_for_claim(session, "R001", trip_ids=["T842792"])
    assert len(history) == 1
    assert await payout_lines.find_for_claim(session, "R002", trip_ids=["T842792"]) == []
    assert await payout_lines.find_for_claim(session, "R001", trip_ids=[]) == []
    with pytest.raises(ValueError):
        await payout_lines.find_for_claim(session, "R001")


async def test_health_and_paginated_apis(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}
    response = await client.get("/ui/riders?limit=2&offset=1")
    assert response.status_code == 200
    assert response.json()["total"] == 40
    assert [r["rider_id"] for r in response.json()["items"]] == ["R002", "R003"]
    assert (await client.get("/ui/riders/R001")).json()["rider_id"] == "R001"
    for path in [
        "/ui/riders/missing",
        "/ui/riders/missing/trips",
        "/ui/riders/missing/payout-lines",
    ]:
        assert (await client.get(path)).status_code == 404
    response = await client.get(
        "/ui/riders/R001/trips",
        params={
            "date_from": "2026-09-12",
            "date_to": "2026-09-12",
            "status": "cancelled_by_rider",
        },
    )
    assert response.status_code == 200 and response.json()["total"] == 1
    item = response.json()["items"][0]
    assert item["trip_id"] == "T842792" and isinstance(item["distance_km"], str)
    response = await client.get(
        "/ui/riders/R001/payout-lines",
        params={
            "date_from": "2026-09-12",
            "date_to": "2026-09-12",
            "line_type": "cancellation_penalty",
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1 and response.json()["items"][0]["amount"] == "-10"
    response = await client.get("/ui/riders/R001/payout-lines?trip_id=T387403")
    assert response.json()["total"] == 1
    assert (await client.get("/ui/riders/R002/payout-lines?trip_id=T387403")).json()["total"] == 0
    for query in [
        "status=not-a-status",
        "date_from=2026-09-22&date_to=2026-09-21",
        "date_from=not-a-date",
        "date_to=9999-12-31",
        "limit=0",
        "offset=-1",
    ]:
        assert (await client.get("/ui/riders/R001/trips?" + query)).status_code == 422
    assert (await client.get("/ui/riders/R001/payout-lines?line_type=invalid")).status_code == 422


async def test_seed_rolls_back_foreign_key_failure(session, tmp_path):
    for filename in ["riders.csv", "trips.csv", "payout_lines.csv"]:
        shutil.copyfile(DEFAULT_DATA_DIR / filename, tmp_path / filename)
    path = tmp_path / "payout_lines.csv"
    rows = list(csv.DictReader(path.open(newline="")))
    rows[0]["trip_id"] = "DOES_NOT_EXIST"
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    before = await session.scalar(select(func.count()).select_from(Rider))
    await session.rollback()
    with pytest.raises(SeedError, match="payout_lines.csv"):
        async with session.begin():
            await seed_data(session, tmp_path)
    assert await session.get(Rider, "R001") is None
    assert await session.scalar(select(func.count()).select_from(Rider)) == before


async def test_seed_validation_failure_before_writes(session, tmp_path):
    for filename in ["riders.csv", "trips.csv", "payout_lines.csv"]:
        shutil.copyfile(DEFAULT_DATA_DIR / filename, tmp_path / filename)
    path = tmp_path / "trips.csv"
    path.write_text(path.read_text().replace(",completed,", ",bad_status,", 1))
    with pytest.raises(SeedError, match="trips.csv: row 2"):
        await seed_data(session, tmp_path)
    assert await session.get(Rider, "R001") is None


async def test_seed_atomic_on_database_failure(connection, session):
    # Transaction-scoped constraint in the disposable test DB forces a later-table failure.
    await connection.exec_driver_sql(
        "ALTER TABLE trips ADD CONSTRAINT test_seed_rejection CHECK (trip_id <> 'T702770')"
    )
    with pytest.raises(SeedError, match="trips.csv"):
        async with session.begin():
            await seed_data(session)
    assert await session.get(Rider, "R001") is None


async def test_seed_cli_from_other_directory_and_failure_exit(database_url, tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env["DATABASE_URL"] = database_url.render_as_string(hide_password=False)
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "app.scripts.seed", "--data-dir", str(tmp_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 1 and "riders.csv" in result.stderr
    assert "Traceback" not in result.stderr
    command = [sys.executable, "-m", "app.scripts.seed"]
    first = await asyncio.to_thread(
        subprocess.run, command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20
    )
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["trips"] == {
        "inserted": 3304,
        "skipped": 10,
        "remapped_rider_references": 64,
    }
    assert "rider_id R7 -> R007" in first.stderr
    assert "rider_id r19 -> R019" in first.stderr
    second = await asyncio.to_thread(
        subprocess.run, command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20
    )
    assert second.returncode == 0, second.stderr
    assert all(counts["inserted"] == 0 for counts in json.loads(second.stdout).values())


async def test_database_session_dependency_rolls_back_and_commits(database_url, monkeypatch):
    engine = create_async_engine(database_url, poolclass=NullPool, hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    key = "S" + uuid4().hex[:20]
    try:
        generator = get_db_session()
        session = await anext(generator)
        session.add(Rider(rider_id=key, name="Rollback", city="Test", joined_on=date.today()))
        await session.flush()
        with pytest.raises(RuntimeError):
            await generator.athrow(RuntimeError("abort request"))
        async with factory() as reader:
            assert await reader.get(Rider, key) is None
        generator = get_db_session()
        session = await anext(generator)
        session.add(Rider(rider_id=key, name="Commit", city="Test", joined_on=date.today()))
        await session.commit()
        await generator.aclose()
        async with factory() as reader:
            assert (await reader.get(Rider, key)).name == "Commit"
    finally:
        await engine.dispose()
