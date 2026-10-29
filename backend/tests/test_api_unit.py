from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from app.core.database import get_db_session
from app.main import create_app
from app.repositories.trips import ist_date_range
from app.scripts.seed import SeedError, read_datasets


async def test_health_failure_is_503_and_sanitized():
    app = create_app()
    session = AsyncMock()
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("private-password"))

    async def unavailable():
        yield session

    app.dependency_overrides[get_db_session] = unavailable
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Database unavailable"
    assert "private-password" not in response.text


async def test_http_validation_and_cors_without_database():
    app = create_app()

    async def unused():
        yield None

    app.dependency_overrides[get_db_session] = unused
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/ui/riders?limit=101")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        response = await client.get("/not-a-route")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "http_404"
        for origin, allowed in [("http://localhost:3000", True), ("http://untrusted.test", False)]:
            response = await client.options(
                "/ui/riders",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert ("access-control-allow-origin" in response.headers) is allowed
        assert (await client.get("/messages")).status_code == 405


def test_source_validation_and_default_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    datasets = read_datasets()
    assert {name: len(rows) for name, rows in datasets.items()} == {
        "riders": 40,
        "trips": 3314,
        "payout_lines": 3222,
    }
    assert datasets["trips"][0]["started_at"].utcoffset() is not None
    with pytest.raises(SeedError, match="riders.csv"):
        read_datasets(tmp_path)


def test_ist_range_validation():
    from datetime import date

    with pytest.raises(ValueError, match="date_from"):
        ist_date_range(date(2026, 9, 22), date(2026, 9, 21))


def test_only_approved_rider_aliases_are_normalized():
    from app.scripts.seed import normalize_rider_reference

    known = {"R007", "R019", "R001"}
    assert normalize_rider_reference("R7", known) == "R007"
    assert normalize_rider_reference("r19", known) == "R019"
    assert normalize_rider_reference("R001", known) == "R001"
    for value in ["r7", "R19", "R999", " R007"]:
        with pytest.raises(SeedError, match="Unknown rider"):
            normalize_rider_reference(value, known)
    for known in [{"R019"}, {"R7", "R007", "R019"}]:
        with pytest.raises(SeedError, match="ambiguous"):
            normalize_rider_reference("R7", known)
