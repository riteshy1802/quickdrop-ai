"""Idempotent CSV import. Run with uv run python -m app.scripts.seed."""

import argparse
import asyncio
import csv
import json
import logging
import sys
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BACKEND_DIR
from app.core.database import get_engine, get_session_factory
from app.data_quality.rules import APPROVED_RIDER_ALIASES as APPROVED_RIDER_ALIASES
from app.data_quality.rules import NormalizationError, canonical_rider_reference
from app.models import PayoutLine, Rider, Trip
from app.schemas.payout import PayoutLineResponse
from app.schemas.rider import RiderResponse
from app.schemas.trip import TripResponse

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = BACKEND_DIR.parent / "data"
DATASETS = (
    (Rider, RiderResponse, "riders.csv", "rider_id"),
    (Trip, TripResponse, "trips.csv", "trip_id"),
    (PayoutLine, PayoutLineResponse, "payout_lines.csv", "line_id"),
)


class SeedError(ValueError):
    """Actionable source-data or import error without database credentials."""


def read_datasets(data_dir: Path = DEFAULT_DATA_DIR) -> dict[str, list[dict]]:
    datasets = {}
    for model, schema, filename, _ in DATASETS:
        path = data_dir / filename
        rows = []
        try:
            with path.open(encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                if set(reader.fieldnames or ()) != set(schema.model_fields) or len(
                    reader.fieldnames or ()
                ) != len(schema.model_fields):
                    raise SeedError(f"{filename}: CSV columns do not match the expected schema")
                for number, row in enumerate(reader, start=2):
                    if None in row or any(value is None for value in row.values()):
                        raise SeedError(f"{filename}: row {number}: incorrect number of CSV fields")
                    try:
                        if "trip_id" in row and row["trip_id"] == "" and model is PayoutLine:
                            row["trip_id"] = None
                        rows.append(schema.model_validate(row).model_dump())
                    except ValidationError as exc:
                        errors = "; ".join(
                            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
                        )
                        raise SeedError(f"{filename}: row {number}: {errors}") from None
        except (OSError, UnicodeError, csv.Error) as exc:
            raise SeedError(f"{filename}: unable to read CSV ({type(exc).__name__})") from None
        datasets[model.__tablename__] = rows
    return datasets


def normalize_rider_reference(rider_id: str, rider_ids: set[str]) -> str:
    """Compatibility wrapper over the shared approved alias rules."""
    try:
        return canonical_rider_reference(rider_id, rider_ids)
    except NormalizationError as exc:
        raise SeedError(str(exc)) from None


async def seed_data(
    session: AsyncSession,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> dict[str, dict[str, int]]:
    """Caller owns the transaction; validate all data and references before inserts."""
    datasets = read_datasets(data_dir)
    rider_ids = {row["rider_id"] for row in datasets["riders"]}
    remapped = {model.__tablename__: 0 for model, _, _, _ in DATASETS}
    # Validate all references and reject conflicting duplicates before any writes.
    for model, _, filename, key in DATASETS:
        seen = {}
        for number, row in enumerate(datasets[model.__tablename__], 2):
            if model is not Rider:
                original = row["rider_id"]
                try:
                    row["rider_id"] = normalize_rider_reference(original, rider_ids)
                except SeedError as exc:
                    raise SeedError(f"{filename}: row {number}: {exc}") from None
                if original != row["rider_id"]:
                    remapped[model.__tablename__] += 1
                    logger.info(
                        "%s row %d: rider_id %s -> %s", filename, number, original, row["rider_id"]
                    )
            previous = seen.setdefault(row[key], row)
            if previous != row:
                raise SeedError(f"{filename}: row {number}: conflicting duplicate ID {row[key]!r}")
    trip_owners = {row["trip_id"]: row["rider_id"] for row in datasets["trips"]}
    for number, row in enumerate(datasets["payout_lines"], 2):
        if row["trip_id"] is not None and trip_owners.get(row["trip_id"]) != row["rider_id"]:
            raise SeedError(
                f"payout_lines.csv: row {number}: trip reference is missing "
                "or belongs to a different rider"
            )
    counts = {}
    for model, _, filename, key in DATASETS:
        rows = datasets[model.__tablename__]
        inserted = 0
        for start in range(0, len(rows), 500):
            statement = (
                insert(model)
                .values(rows[start : start + 500])
                .on_conflict_do_nothing(
                    index_elements=[key],
                )
                .returning(getattr(model, key))
            )
            try:
                result = await session.scalars(statement)
            except SQLAlchemyError as exc:
                raise SeedError(
                    f"{filename}: import failed near rows {start + 2}–{start + 501}; "
                    f"check references and constraints ({type(exc).__name__})"
                ) from None
            inserted += len(result.all())
        counts[model.__tablename__] = {"inserted": inserted, "skipped": len(rows) - inserted}
        if model is Trip or remapped[model.__tablename__]:
            counts[model.__tablename__]["remapped_rider_references"] = remapped[model.__tablename__]
    return counts


async def run(data_dir: Path) -> dict[str, dict[str, int]]:
    try:
        async with get_session_factory()() as session, session.begin():
            return await seed_data(session, data_dir)
    finally:
        await get_engine().dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        counts = asyncio.run(run(args.data_dir))
    except (SeedError, SQLAlchemyError, OSError, ValueError) as exc:
        message = str(exc) if isinstance(exc, SeedError) else type(exc).__name__
        print(f"Seed failed; import rolled back: {message}", file=sys.stderr)
        return 1
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
