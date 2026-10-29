import csv

import pytest
from sqlalchemy import event, select, text, update
from sqlalchemy.exc import IntegrityError

from app.data_quality.normalize import normalize_sources
from app.data_quality.sync import synchronize
from app.models import (
    AgentTrace,
    Conversation,
    Dispute,
    DisputeItem,
    PaymentIntent,
    PayoutLine,
    Rider,
    Trip,
)
from app.scripts.seed import DEFAULT_DATA_DIR
from app.services.financial.reconciliation import reconcile
from app.services.financial.types import ClaimRequest, PaymentEvidence

pytestmark = pytest.mark.database


async def source_rows(session, model):
    return [dict(r) for r in (await session.execute(select(model.__table__))).mappings()]


async def test_dry_run_select_only_and_idempotent_apply(session, connection, seeded):
    bundle = normalize_sources(DEFAULT_DATA_DIR)
    payouts = await source_rows(session, PayoutLine)
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(connection.sync_connection, "before_cursor_execute", record)
    try:
        plan = await synchronize(session, bundle)
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", record)
    assert all(q.lstrip().upper().startswith("SELECT") for q in statements)
    assert plan["operations"]["trips"] == {"insert": 0, "update": 1, "skip": 3303, "conflict": 0}
    assert plan["applied"] == {"inserted": 0, "updated": 0}
    assert await session.scalar(select(Trip.distance_km).where(Trip.trip_id == "T312538")) == 5000
    applied = await synchronize(session, bundle, apply=True)
    await session.commit()
    assert applied["applied"] == {"inserted": 0, "updated": 1}
    assert await session.scalar(select(Trip.distance_km).where(Trip.trip_id == "T312538")) == 5
    assert await source_rows(session, PayoutLine) == payouts
    second = await synchronize(session, bundle, apply=True)
    assert second["applied"] == {"inserted": 0, "updated": 0}
    assert sum(s["skip"] for s in second["operations"].values()) == 6566
    assert await source_rows(session, PayoutLine) == payouts


@pytest.mark.parametrize(
    "history", ["RESOLVED", "PENDING", "UNKNOWN", "SUCCEEDED", "trace", "message", "context"]
)
async def test_prior_decision_history_blocks_basis_rewrite(session, seeded, history):
    conversation = Conversation(
        rider_id="R031", context={"trip_id": "T312538"} if history == "context" else {}
    )
    session.add(conversation)
    await session.flush()
    if history in {"RESOLVED", "PENDING", "UNKNOWN", "SUCCEEDED"}:
        dispute = Dispute(
            conversation_id=conversation.id,
            rider_id="R031",
            status="RESOLVED" if history == "RESOLVED" else "PAYMENT_PENDING",
        )
        session.add(dispute)
        await session.flush()
        session.add(
            DisputeItem(
                dispute_id=dispute.id,
                source_type="trip",
                source_id="T312538",
                expected_amount=65,
                actual_amount=43,
                difference=22,
            )
        )
        if history != "RESOLVED":
            session.add(
                PaymentIntent(
                    dispute_id=dispute.id,
                    rider_id="R031",
                    amount=22,
                    status=history,
                    payment_type="OPS_APPROVED",
                    idempotency_key="test-history",
                )
            )
    elif history == "trace":
        session.add(
            AgentTrace(
                conversation_id=conversation.id,
                type="decision",
                name="prior-financial-basis",
                input={"trip_id": "T312538", "distance_km": "5000"},
            )
        )
    elif history == "message":
        from app.models import Message

        session.add(
            Message(
                conversation_id=conversation.id, sender_type="OPS", content="Prior case decision"
            )
        )
    await session.commit()
    plan = await synchronize(session, normalize_sources(DEFAULT_DATA_DIR), apply=True)
    assert plan["status"] == "blocked" and plan["conflicts"]
    assert plan["applied"] == {"inserted": 0, "updated": 0}
    assert await session.scalar(select(Trip.distance_km).where(Trip.trip_id == "T312538")) == 5000


async def test_payout_drift_blocks_all_changes(session, seeded):
    await session.execute(
        update(PayoutLine).where(PayoutLine.line_id == "PL000001").values(amount=999)
    )
    await session.commit()
    plan = await synchronize(session, normalize_sources(DEFAULT_DATA_DIR), apply=True)
    assert plan["status"] == "blocked"
    assert any(c.get("source_id") == "PL000001" for c in plan["conflicts"])
    assert await session.scalar(select(Trip.distance_km).where(Trip.trip_id == "T312538")) == 5000
    assert (
        await session.scalar(select(PayoutLine.amount).where(PayoutLine.line_id == "PL000001"))
        == 999
    )


def tiny_sources(tmp_path):
    sources = {
        "riders.csv": [
            dict(rider_id="R900", name="Sync test rider", city="Test", joined_on="2026-01-01")
        ],
        "trips.csv": [
            dict(
                trip_id="TSYNC900",
                rider_id="R900",
                started_at="2026-09-20T08:00:00Z",
                status="completed",
                distance_km="3",
                surge_multiplier="1",
            )
        ],
        "payout_lines.csv": [
            dict(
                line_id="PLSYNC900",
                payout_date="2026-09-20",
                rider_id="R900",
                line_type="trip",
                trip_id="TSYNC900",
                amount="31",
            )
        ],
    }
    for name, rows in sources.items():
        with (tmp_path / name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return normalize_sources(tmp_path)


async def test_missing_records_insert_once_preserving_unrelated_data(session, tmp_path):
    before = await source_rows(session, Rider)
    bundle = tiny_sources(tmp_path)
    first = await synchronize(session, bundle, apply=True)
    await session.commit()
    assert first["applied"] == {"inserted": 3, "updated": 0}
    second = await synchronize(session, bundle, apply=True)
    assert second["applied"] == {"inserted": 0, "updated": 0}
    assert await session.get(Rider, "R900") is not None
    assert len(await source_rows(session, Rider)) == len(before) + 1


async def test_sql_failure_rolls_back_every_insert(session, connection, tmp_path):
    bundle = tiny_sources(tmp_path)
    await connection.execute(
        text(
            "ALTER TABLE payout_lines ADD CONSTRAINT sync_test_failure "
            "CHECK (line_id <> 'PLSYNC900')"
        )
    )
    with pytest.raises(IntegrityError):
        async with session.begin():
            await synchronize(session, bundle, apply=True)
    assert await session.get(Rider, "R900") is None
    assert await session.get(Trip, "TSYNC900") is None


async def test_normalized_db_values_keep_financial_provenance(session, seeded):
    await synchronize(session, normalize_sources(DEFAULT_DATA_DIR), apply=True)
    await session.commit()
    from datetime import datetime

    result = await reconcile(
        session,
        ClaimRequest(
            rider_id="R031",
            received_at=datetime.fromisoformat("2026-09-23T10:00:00+05:30"),
            trip_ids=("T312538",),
        ),
        source_data_complete=True,
        evidence=PaymentEvidence(rider_id="R031", provider_history_complete=True),
    )
    assert (
        result.expected_amount == 65 and result.historical_paid == 43 and result.outstanding == 22
    )
    assert result.items[0].data_quality == "CORRECTED"
    assert result.data_quality_transformations[0].original_value == "5000"
    assert await session.scalar(select(Trip.distance_km).where(Trip.trip_id == "T312538")) == 5


async def test_existing_decision_blocks_insertion_of_missing_historical_sources(session, seeded):
    # A payout import can change a prior decision's basis just as a distance UPDATE can.
    from sqlalchemy import delete

    conversation = Conversation(rider_id="R031")
    session.add(conversation)
    await session.flush()
    session.add(Dispute(rider_id="R031", conversation_id=conversation.id, status="RESOLVED"))
    await session.execute(delete(PayoutLine).where(PayoutLine.line_id == "PL002492"))
    # Pretend the approved distance was already synchronized so this plan contains only an insert.
    await session.execute(update(Trip).where(Trip.trip_id == "T312538").values(distance_km=5))
    await session.commit()
    plan = await synchronize(session, normalize_sources(DEFAULT_DATA_DIR), apply=True)
    assert plan["operations"]["trips"]["update"] == 0
    assert plan["operations"]["payout_lines"]["insert"] == 1
    assert plan["status"] == "blocked" and plan["applied"]["inserted"] == 0
    assert await session.get(PayoutLine, "PL002492") is None
