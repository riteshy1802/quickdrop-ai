"""Audit, classify and synchronize sources. Explicit --dry-run or --apply is required."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import BACKEND_DIR, get_settings
from app.core.database import get_engine, get_session_factory
from app.data_quality.audit import analyze_distance_pattern
from app.data_quality.normalize import normalize_sources
from app.data_quality.rules import NormalizationError
from app.data_quality.sync import synchronize
from app.scripts.audit_data import audit_data
from app.scripts.seed import DEFAULT_DATA_DIR


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


async def run(data_dir: Path, *, apply: bool, report_path: Path) -> tuple[dict, int]:
    try:
        bundle = normalize_sources(data_dir)
    except NormalizationError as exc:
        report = {"status": "invalid_sources", "error": str(exc), "raw_audit": audit_data(data_dir)}
        write_report(report_path, report)
        return report, 1
    report = dict(bundle.report)
    report["distance_investigation"] = analyze_distance_pattern(bundle)
    url = get_settings().sqlalchemy_url
    # These source synchronization commands target the local development Compose setup only.
    if url.host not in {"localhost", "127.0.0.1", "::1", "postgres"}:
        raise NormalizationError(
            "Refusing synchronization outside the local development PostgreSQL host"
        )
    try:
        async with get_session_factory()() as session, session.begin():
            if not apply:
                await session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
            plan = await synchronize(session, bundle, apply=apply)
            plan["connection"] = {
                "host": url.host,
                "port": url.port or 5432,
                "database": url.database,
            }
            report["synchronization"] = plan
            # Persist the inspected plan before committing.
            # Failed report writes roll back the DB transaction.
            write_report(report_path, report)
        if plan["status"] == "applied_in_transaction":
            plan["status"] = "applied"
        write_report(report_path, report)
        return report, 1 if plan["conflicts"] else 0
    except (SQLAlchemyError, NormalizationError) as exc:
        report["synchronization"] = {"status": "rolled_back", "error_type": type(exc).__name__}
        write_report(report_path, report)
        return report, 1
    finally:
        await get_engine().dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--report", type=Path, default=BACKEND_DIR / "reports/data_quality.json")
    args = parser.parse_args()
    try:
        report, code = asyncio.run(run(args.data_dir, apply=args.apply, report_path=args.report))
    except (OSError, ValueError) as exc:
        print(f"Synchronization failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "report": str(args.report),
                "classification_counts": report.get("classification_counts"),
                "synchronization": report.get("synchronization", {"status": report.get("status")}),
            },
            indent=2,
            default=str,
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
