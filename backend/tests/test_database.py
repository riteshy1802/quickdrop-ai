import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from conftest import migrate
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import BACKEND_DIR
from app.models import (
    AgentTrace,
    Base,
    Conversation,
    Dispute,
    DisputeItem,
    Message,
    OpsQueue,
    OpsUser,
    PaymentIntent,
    PayoutLine,
    Rider,
    Trip,
)

pytestmark = pytest.mark.database

DAY = date(2026, 10, 29)  # Explicit IST business date, not a UTC timestamp cast.


async def case(conn):
    rider = "R" + uuid4().hex[:20]
    await conn.execute(
        Rider.__table__.insert().values(
            rider_id=rider,
            name="Test rider",
            city="Bengaluru",
            joined_on=DAY,
        )
    )
    conversation = (
        await conn.execute(
            Conversation.__table__.insert()
            .values(
                rider_id=rider,
            )
            .returning(Conversation.id)
        )
    ).scalar_one()
    dispute = (
        await conn.execute(
            Dispute.__table__.insert()
            .values(
                rider_id=rider,
                conversation_id=conversation,
                verified_amount=Decimal("425"),
            )
            .returning(Dispute.id)
        )
    ).scalar_one()
    return rider, conversation, dispute


def payment(rider, dispute, **overrides):
    values = dict(
        rider_id=rider,
        dispute_id=dispute,
        amount=Decimal("25"),
        payment_type="AUTO",
        auto_pay_date=DAY,
        idempotency_key=uuid4().hex,
    )
    values.update(overrides)
    return PaymentIntent.__table__.insert().values(**values)


async def rejected(conn, statement):
    with pytest.raises(IntegrityError):
        async with conn.begin_nested():
            await conn.execute(statement)


@pytest.mark.parametrize("amount", ["0", "-1", "0.5", "1.0001", "NaN", "Infinity", "-Infinity"])
async def test_reject_invalid_payment_amount(connection, amount):
    rider, _, dispute = await case(connection)
    await rejected(
        connection,
        payment(
            rider,
            dispute,
            amount=Decimal(amount),
            payment_type="OPS_APPROVED",
            auto_pay_date=None,
        ),
    )


async def test_auto_cap_and_human_approved_amount(connection):
    rider, _, dispute = await case(connection)
    await rejected(connection, payment(rider, dispute, amount=Decimal("201")))
    await rejected(connection, payment(rider, dispute, auto_pay_date=None))
    await rejected(connection, payment(rider, dispute, payment_type="OPS_APPROVED"))
    await rejected(connection, payment(rider, dispute, retry_count=-1))
    await connection.execute(payment(rider, dispute, amount=Decimal("200")))
    await connection.execute(
        payment(
            rider,
            dispute,
            amount=Decimal("425"),
            payment_type="OPS_APPROVED",
            auto_pay_date=None,
        )
    )


@pytest.mark.parametrize(
    "status",
    [
        "PENDING",
        "AWAITING_APPROVAL",
        "PROCESSING",
        "UNKNOWN",
        "SUCCEEDED",
        "FAILED",
        "NEEDS_REVIEW",
    ],
)
async def test_auto_reservation_survives_every_status(connection, status):
    rider, conversation, dispute = await case(connection)
    other_dispute = (
        await connection.execute(
            Dispute.__table__.insert()
            .values(
                rider_id=rider,
                conversation_id=conversation,
            )
            .returning(Dispute.id)
        )
    ).scalar_one()
    await connection.execute(payment(rider, dispute, status=status))
    await rejected(connection, payment(rider, other_dispute))
    await connection.execute(payment(rider, other_dispute, auto_pay_date=DAY + timedelta(days=1)))
    other_rider, _, other_claim = await case(connection)
    await connection.execute(payment(other_rider, other_claim))


async def test_unique_idempotency_and_webhook_replay(connection):
    rider, conversation, dispute = await case(connection)
    await connection.execute(payment(rider, dispute, idempotency_key="same-key"))
    await rejected(
        connection,
        payment(
            rider,
            dispute,
            idempotency_key="same-key",
            auto_pay_date=DAY + timedelta(days=1),
        ),
    )
    message = Message.__table__.insert().values(
        conversation_id=conversation,
        message_id="incoming-1",
        sender_type="RIDER",
        content="Missing surge",
        processing_status="COMPLETED",
        webhook_reply="Verified reply",
    )
    await connection.execute(message)
    await rejected(connection, message)
    assert (
        await connection.execute(
            select(Message.webhook_reply).where(
                Message.message_id == "incoming-1",
            )
        )
    ).scalar_one() == "Verified reply"
    for _ in range(2):
        await connection.execute(
            Message.__table__.insert().values(
                conversation_id=conversation,
                sender_type="AI",
                content="Reply",
            )
        )
    await connection.execute(
        Message.__table__.insert().values(
            conversation_id=conversation,
            sender_type="OPS",
            content="Private note",
            is_internal=True,
        )
    )
    await rejected(
        connection,
        Message.__table__.insert().values(
            conversation_id=conversation,
            sender_type="RIDER",
            content="Invalid",
            is_internal=True,
        ),
    )


async def test_negative_history_decimal_precision_and_ownership(connection):
    rider, _, dispute = await case(connection)
    other, _, _ = await case(connection)
    trip = "T" + uuid4().hex[:20]
    await connection.execute(
        Trip.__table__.insert().values(
            trip_id=trip,
            rider_id=rider,
            started_at=datetime.now(UTC),
            status="cancelled_by_rider",
            distance_km=Decimal("2.123456789"),
            surge_multiplier=Decimal("1.25"),
        )
    )
    line = dict(
        line_id="line-1",
        rider_id=rider,
        trip_id=trip,
        payout_date=DAY,
        line_type="cancellation_penalty",
        amount=Decimal("-25.50"),
    )
    await connection.execute(PayoutLine.__table__.insert().values(**line))
    assert (await connection.execute(select(PayoutLine.amount))).scalar_one() == Decimal("-25.50")
    assert (await connection.execute(select(Trip.distance_km))).scalar_one() == Decimal(
        "2.123456789"
    )
    await connection.execute(
        PayoutLine.__table__.insert().values(
            line_id="daily",
            rider_id=rider,
            payout_date=DAY,
            line_type="daily_incentive",
            amount=25,
        )
    )
    await rejected(
        connection,
        PayoutLine.__table__.insert().values(
            **{**line, "line_id": "wrong-owner", "rider_id": other},
        ),
    )
    await rejected(connection, payment(other, dispute))
    await connection.execute(
        DisputeItem.__table__.insert().values(
            dispute_id=dispute,
            source_type="penalty",
            source_id=trip,
            expected_amount=-25,
            actual_amount=-50,
            difference=25,
        )
    )


async def test_json_defaults_timestamps_and_ops_queue(connection):
    rider, conversation, dispute = await case(connection)
    row = (
        await connection.execute(
            select(
                Conversation.context,
                Conversation.created_at,
                Conversation.handling_mode,
            ).where(Conversation.id == conversation)
        )
    ).one()
    assert row.context == {} and row.created_at.tzinfo is not None and row.handling_mode == "AI"
    data = {"trip_ids": ["T1"], "clarification": {"missing": True}}
    await connection.execute(
        Conversation.__table__.update()
        .where(
            Conversation.id == conversation,
        )
        .values(context=data)
    )
    assert (
        await connection.execute(
            select(Conversation.context).where(
                Conversation.id == conversation,
            )
        )
    ).scalar_one() == data
    await rejected(
        connection,
        Conversation.__table__.update()
        .where(
            Conversation.id == conversation,
        )
        .values(context=["not-an-object"]),
    )
    await connection.execute(
        AgentTrace.__table__.insert().values(
            conversation_id=conversation,
            type="reply",
            name="response",
            input=None,
            output="Public reply",
        )
    )
    assert (await connection.execute(select(AgentTrace.output))).scalar_one() == "Public reply"
    assert (
        await connection.execute(
            select(Dispute.details).where(
                Dispute.id == dispute,
            )
        )
    ).scalar_one() == {}
    operator = (
        await connection.execute(
            OpsUser.__table__.insert()
            .values(
                email="admin@example.test",
                password_hash="a-test-hash",
            )
            .returning(OpsUser.id)
        )
    ).scalar_one()
    await rejected(
        connection,
        OpsUser.__table__.insert().values(
            email="ADMIN@example.test",
            password_hash="another-test-hash",
        ),
    )
    await connection.execute(
        OpsQueue.__table__.insert().values(
            dispute_id=dispute,
            type="approval",
            amount=425,
            reason="Over auto threshold",
            assigned_to=operator,
        )
    )
    await rejected(
        connection,
        OpsQueue.__table__.insert().values(
            dispute_id=dispute,
            type="approval",
            reason="Missing amount",
        ),
    )


async def test_concurrent_daily_reservation(database_url):
    engine = create_async_engine(database_url, poolclass=NullPool, hide_parameters=True)
    first_inserted = asyncio.Event()
    second_attempted = asyncio.Event()
    async with engine.begin() as conn:
        rider, _, dispute = await case(conn)

    async def first():
        async with engine.begin() as conn:
            await conn.execute(payment(rider, dispute))
            first_inserted.set()
            await second_attempted.wait()
            await asyncio.sleep(0.1)  # Hold the first transaction open during the second insert.

    async def second():
        await first_inserted.wait()
        async with engine.begin() as conn:
            second_attempted.set()
            await conn.execute(payment(rider, dispute))

    try:
        results = await asyncio.wait_for(
            asyncio.gather(first(), second(), return_exceptions=True),
            timeout=10,
        )
        assert results[0] is None
        assert isinstance(results[1], IntegrityError)
        async with engine.connect() as conn:
            assert (
                await conn.execute(
                    select(func.count())
                    .select_from(PaymentIntent)
                    .where(
                        PaymentIntent.rider_id == rider,
                    )
                )
            ).scalar_one() == 1
    finally:
        # This test commits to exercise concurrency; clean up only its own test records.
        async with engine.begin() as conn:
            await conn.execute(delete(PaymentIntent).where(PaymentIntent.rider_id == rider))
            await conn.execute(delete(Dispute).where(Dispute.id == dispute))
            await conn.execute(delete(Conversation).where(Conversation.rider_id == rider))
            await conn.execute(delete(Rider).where(Rider.rider_id == rider))
        await engine.dispose()


async def test_migration_and_database_catalog(connection, database_url):
    tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
    assert set(tables) == set(Base.metadata.tables) | {"alembic_version"}
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert (
        await connection.execute(text("SELECT version_num FROM alembic_version"))
    ).scalar_one() == head
    indexes = await connection.run_sync(lambda conn: inspect(conn).get_indexes("payment_intents"))
    reservation = next(i for i in indexes if i["name"] == "uq_payment_intents_auto_rider_day")
    assert reservation["unique"]
    predicate = reservation["dialect_options"]["postgresql_where"]
    assert "AUTO" in predicate and "status" not in predicate
    assert "No new upgrade operations detected" in migrate(database_url, "check")
