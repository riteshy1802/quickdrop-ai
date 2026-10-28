"""initial quickdrop schema

Revision ID: 078eb21553bb
Revises:
Create Date: 2026-10-29 02:58:18.863773

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "078eb21553bb"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Reviewed initial schema; dependencies precede their referencing tables.
    op.create_table(
        "ops_users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ops_users")),
        sa.UniqueConstraint("email", name=op.f("uq_ops_users_email")),
    )
    op.create_index(
        "uq_ops_users_email_lower", "ops_users", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_table(
        "riders",
        sa.Column("rider_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("joined_on", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("rider_id", name=op.f("pk_riders")),
    )
    op.create_table(
        "conversations",
        sa.Column("rider_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="OPEN", nullable=False),
        sa.Column("handling_mode", sa.String(length=16), server_default="AI", nullable=False),
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "handling_mode IN ('AI','HUMAN')", name=op.f("ck_conversations_handling_mode")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(context) = 'object'", name=op.f("ck_conversations_context_object")
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','AWAITING_INFORMATION','AWAITING_APPROVAL','ESCALATED',"
            "'HUMAN_HANDLING','PAYMENT_PENDING','RESOLVED')",
            name=op.f("ck_conversations_status"),
        ),
        sa.ForeignKeyConstraint(
            ["rider_id"],
            ["riders.rider_id"],
            name=op.f("fk_conversations_rider_id_riders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.UniqueConstraint("id", "rider_id", name="uq_conversations_id_rider"),
    )
    op.create_index(
        "ix_conversations_rider_updated", "conversations", ["rider_id", "updated_at"], unique=False
    )
    op.create_index(
        "ix_conversations_status_updated", "conversations", ["status", "updated_at"], unique=False
    )
    op.create_table(
        "trips",
        sa.Column("trip_id", sa.String(length=32), nullable=False),
        sa.Column("rider_id", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("distance_km", sa.Numeric(), nullable=False),
        sa.Column("surge_multiplier", sa.Numeric(), nullable=False),
        sa.CheckConstraint(
            "distance_km >= 0 AND distance_km < 'Infinity'::numeric", name=op.f("ck_trips_distance")
        ),
        sa.CheckConstraint(
            "status IN ('completed','cancelled_by_customer','cancelled_by_rider')",
            name=op.f("ck_trips_status"),
        ),
        sa.CheckConstraint(
            "surge_multiplier > 0 AND surge_multiplier < 'Infinity'::numeric",
            name=op.f("ck_trips_surge"),
        ),
        sa.ForeignKeyConstraint(
            ["rider_id"],
            ["riders.rider_id"],
            name=op.f("fk_trips_rider_id_riders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("trip_id", name=op.f("pk_trips")),
        sa.UniqueConstraint("trip_id", "rider_id", name="uq_trips_trip_rider"),
    )
    op.create_index("ix_trips_rider_started", "trips", ["rider_id", "started_at"], unique=False)
    op.create_table(
        "agent_traces",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "input", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "output", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('message_in','tool_call','decision','reply','error')",
            name=op.f("ck_agent_traces_type"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_agent_traces_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_traces")),
    )
    op.create_index(
        "ix_agent_traces_conversation_created",
        "agent_traces",
        ["conversation_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "disputes",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("rider_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="OPEN", nullable=False),
        sa.Column("claimed_amount", sa.Numeric(), nullable=True),
        sa.Column("verified_amount", sa.Numeric(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "claimed_amount IS NULL OR (claimed_amount >= 0 AND claimed_amount < "
            "'Infinity'::numeric)",
            name=op.f("ck_disputes_claimed_amount"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(details) = 'object'", name=op.f("ck_disputes_details_object")
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','INVESTIGATING','AWAITING_INFORMATION',"
            "'AWAITING_APPROVAL','VERIFIED','PAYMENT_PENDING','RESOLVED','REJECTED','ESCALATED')",
            name=op.f("ck_disputes_status"),
        ),
        sa.CheckConstraint(
            "verified_amount IS NULL OR (verified_amount >= 0 AND verified_amount < "
            "'Infinity'::numeric)",
            name=op.f("ck_disputes_verified_amount"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "rider_id"],
            ["conversations.id", "conversations.rider_id"],
            name="fk_disputes_conversation_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rider_id"],
            ["riders.rider_id"],
            name=op.f("fk_disputes_rider_id_riders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disputes")),
        sa.UniqueConstraint("id", "rider_id", name="uq_disputes_id_rider"),
    )
    op.create_index(
        "ix_disputes_conversation_owner", "disputes", ["conversation_id", "rider_id"], unique=False
    )
    op.create_index(
        "ix_disputes_rider_created", "disputes", ["rider_id", "created_at"], unique=False
    )
    op.create_table(
        "messages",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("sender_type", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("processing_status", sa.String(length=24), nullable=True),
        sa.Column("webhook_reply", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "NOT is_internal OR sender_type = 'OPS'", name=op.f("ck_messages_internal_ops_only")
        ),
        sa.CheckConstraint(
            "message_id IS NULL OR sender_type = 'RIDER'", name=op.f("ck_messages_webhook_sender")
        ),
        sa.CheckConstraint(
            "processing_status IS NULL OR processing_status IN ('RECEIVED',"
            "'PROCESSING','COMPLETED','FAILED')",
            name=op.f("ck_messages_processing_status"),
        ),
        sa.CheckConstraint(
            "sender_type IN ('RIDER','AI','OPS')", name=op.f("ck_messages_sender_type")
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint("message_id", name=op.f("uq_messages_message_id")),
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "payout_lines",
        sa.Column("line_id", sa.String(length=40), nullable=False),
        sa.Column("rider_id", sa.String(length=32), nullable=False),
        sa.Column("trip_id", sa.String(length=32), nullable=True),
        sa.Column("payout_date", sa.Date(), nullable=False),
        sa.Column("line_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.CheckConstraint(
            "amount > '-Infinity'::numeric AND amount < 'Infinity'::numeric",
            name=op.f("ck_payout_lines_finite_amount"),
        ),
        sa.CheckConstraint(
            "line_type = 'daily_incentive' OR trip_id IS NOT NULL",
            name=op.f("ck_payout_lines_trip_reference"),
        ),
        sa.CheckConstraint(
            "line_type IN ('trip','daily_incentive','cancellation_penalty')",
            name=op.f("ck_payout_lines_line_type"),
        ),
        sa.ForeignKeyConstraint(
            ["rider_id"],
            ["riders.rider_id"],
            name=op.f("fk_payout_lines_rider_id_riders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id", "rider_id"],
            ["trips.trip_id", "trips.rider_id"],
            name="fk_payout_lines_trip_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("line_id", name=op.f("pk_payout_lines")),
    )
    op.create_index(
        "ix_payout_lines_rider_date_type",
        "payout_lines",
        ["rider_id", "payout_date", "line_type"],
        unique=False,
    )
    op.create_index(
        "ix_payout_lines_trip_owner", "payout_lines", ["trip_id", "rider_id"], unique=False
    )
    op.create_table(
        "dispute_items",
        sa.Column("dispute_id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("expected_amount", sa.Numeric(), nullable=False),
        sa.Column("actual_amount", sa.Numeric(), nullable=False),
        sa.Column("difference", sa.Numeric(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "expected_amount > '-Infinity'::numeric AND expected_amount < "
            "'Infinity'::numeric AND actual_amount > '-Infinity'::numeric AND "
            "actual_amount < 'Infinity'::numeric AND difference > "
            "'-Infinity'::numeric AND difference < 'Infinity'::numeric",
            name=op.f("ck_dispute_items_finite_amounts"),
        ),
        sa.CheckConstraint(
            "source_type IN ('trip','incentive','penalty')",
            name=op.f("ck_dispute_items_source_type"),
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"],
            ["disputes.id"],
            name=op.f("fk_dispute_items_dispute_id_disputes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dispute_items")),
    )
    op.create_index(
        op.f("ix_dispute_items_dispute_id"), "dispute_items", ["dispute_id"], unique=False
    )
    op.create_table(
        "ops_queue",
        sa.Column("dispute_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("assigned_to", sa.UUID(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount IS NULL OR (amount >= 0 AND amount < 'Infinity'::numeric)",
            name=op.f("ck_ops_queue_amount"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','IN_REVIEW','APPROVED','REJECTED','RESOLVED')",
            name=op.f("ck_ops_queue_status"),
        ),
        sa.CheckConstraint(
            "type != 'approval' OR amount IS NOT NULL", name=op.f("ck_ops_queue_approval_amount")
        ),
        sa.CheckConstraint("type IN ('approval','escalation')", name=op.f("ck_ops_queue_type")),
        sa.ForeignKeyConstraint(
            ["assigned_to"],
            ["ops_users.id"],
            name=op.f("fk_ops_queue_assigned_to_ops_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"],
            ["disputes.id"],
            name=op.f("fk_ops_queue_dispute_id_disputes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ops_queue")),
    )
    op.create_index(op.f("ix_ops_queue_assigned_to"), "ops_queue", ["assigned_to"], unique=False)
    op.create_index(op.f("ix_ops_queue_dispute_id"), "ops_queue", ["dispute_id"], unique=False)
    op.create_index(
        "ix_ops_queue_pending_created",
        "ops_queue",
        ["status", "created_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('PENDING','IN_REVIEW')"),
    )
    op.create_table(
        "payment_intents",
        sa.Column("dispute_id", sa.Uuid(), nullable=False),
        sa.Column("rider_id", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="PENDING", nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payment_type", sa.String(length=16), nullable=False),
        sa.Column("auto_pay_date", sa.Date(), nullable=True),
        sa.Column("provider_payout_id", sa.String(length=255), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(payment_type = 'AUTO' AND auto_pay_date IS NOT NULL) OR (payment_type = "
            "'OPS_APPROVED' AND auto_pay_date IS NULL)",
            name=op.f("ck_payment_intents_auto_date"),
        ),
        sa.CheckConstraint(
            "amount > 0 AND amount < 'Infinity'::numeric AND amount = trunc(amount)",
            name=op.f("ck_payment_intents_positive_whole_amount"),
        ),
        sa.CheckConstraint(
            "payment_type != 'AUTO' OR amount <= 200",
            name=op.f("ck_payment_intents_auto_amount_limit"),
        ),
        sa.CheckConstraint(
            "payment_type IN ('AUTO','OPS_APPROVED')", name=op.f("ck_payment_intents_payment_type")
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','AWAITING_APPROVAL','PROCESSING','UNKNOWN',"
            "'SUCCEEDED','FAILED','NEEDS_REVIEW')",
            name=op.f("ck_payment_intents_status"),
        ),
        sa.CheckConstraint("retry_count >= 0", name=op.f("ck_payment_intents_retry_count")),
        sa.ForeignKeyConstraint(
            ["dispute_id", "rider_id"],
            ["disputes.id", "disputes.rider_id"],
            name="fk_payment_intents_dispute_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rider_id"],
            ["riders.rider_id"],
            name=op.f("fk_payment_intents_rider_id_riders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_intents")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_payment_intents_idempotency_key")),
    )
    op.create_index(
        "ix_payment_intents_dispute_owner",
        "payment_intents",
        ["dispute_id", "rider_id"],
        unique=False,
    )
    op.create_index(
        "ix_payment_intents_lease", "payment_intents", ["lease_expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_payment_intents_rider_id"), "payment_intents", ["rider_id"], unique=False
    )
    op.create_index(
        "ix_payment_intents_status_retry",
        "payment_intents",
        ["status", "next_retry_at"],
        unique=False,
    )
    op.create_index(
        "uq_payment_intents_auto_rider_day",
        "payment_intents",
        ["rider_id", "auto_pay_date"],
        unique=True,
        postgresql_where=sa.text("payment_type = 'AUTO'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Reviewed initial schema; dependencies precede their referencing tables.
    op.drop_index(
        "uq_payment_intents_auto_rider_day",
        table_name="payment_intents",
        postgresql_where=sa.text("payment_type = 'AUTO'"),
    )
    op.drop_index("ix_payment_intents_status_retry", table_name="payment_intents")
    op.drop_index(op.f("ix_payment_intents_rider_id"), table_name="payment_intents")
    op.drop_index("ix_payment_intents_lease", table_name="payment_intents")
    op.drop_index("ix_payment_intents_dispute_owner", table_name="payment_intents")
    op.drop_table("payment_intents")
    op.drop_index(
        "ix_ops_queue_pending_created",
        table_name="ops_queue",
        postgresql_where=sa.text("status IN ('PENDING','IN_REVIEW')"),
    )
    op.drop_index(op.f("ix_ops_queue_dispute_id"), table_name="ops_queue")
    op.drop_index(op.f("ix_ops_queue_assigned_to"), table_name="ops_queue")
    op.drop_table("ops_queue")
    op.drop_index(op.f("ix_dispute_items_dispute_id"), table_name="dispute_items")
    op.drop_table("dispute_items")
    op.drop_index("ix_payout_lines_trip_owner", table_name="payout_lines")
    op.drop_index("ix_payout_lines_rider_date_type", table_name="payout_lines")
    op.drop_table("payout_lines")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_disputes_rider_created", table_name="disputes")
    op.drop_index("ix_disputes_conversation_owner", table_name="disputes")
    op.drop_table("disputes")
    op.drop_index("ix_agent_traces_conversation_created", table_name="agent_traces")
    op.drop_table("agent_traces")
    op.drop_index("ix_trips_rider_started", table_name="trips")
    op.drop_table("trips")
    op.drop_index("ix_conversations_status_updated", table_name="conversations")
    op.drop_index("ix_conversations_rider_updated", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("riders")
    op.drop_index("uq_ops_users_email_lower", table_name="ops_users")
    op.drop_table("ops_users")
