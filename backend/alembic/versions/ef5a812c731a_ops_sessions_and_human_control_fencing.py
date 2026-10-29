"""ops sessions and human control fencing

Revision ID: ef5a812c731a
Revises: 5a6f842e91d0
Create Date: 2026-10-29 10:33:05.806238

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ef5a812c731a"
down_revision: Union[str, Sequence[str], None] = "5a6f842e91d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ops_login_limits",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_ops_login_limits")),
    )
    op.create_table(
        "ops_sessions",
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("operator_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["ops_users.id"],
            name=op.f("fk_ops_sessions_operator_id_ops_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("digest", name=op.f("pk_ops_sessions")),
    )
    op.create_index(
        op.f("ix_ops_sessions_expires_at"), "ops_sessions", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_ops_sessions_operator_id"),
        "ops_sessions",
        ["operator_id"],
        unique=False,
    )
    op.add_column(
        "conversations", sa.Column("assigned_operator_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "conversations",
        sa.Column("control_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index(
        op.f("ix_conversations_assigned_operator_id"),
        "conversations",
        ["assigned_operator_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_conversations_assigned_operator_id_ops_users"),
        "conversations",
        "ops_users",
        ["assigned_operator_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("messages", sa.Column("operator_id", sa.UUID(), nullable=True))
    op.create_index("ix_messages_operator_id", "messages", ["operator_id"])
    op.add_column("messages", sa.Column("client_request_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_messages_client_request_id"), "messages", ["client_request_id"]
    )
    op.create_foreign_key(
        op.f("fk_messages_operator_id_ops_users"),
        "messages",
        "ops_users",
        ["operator_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_messages_operator_id_ops_users"), "messages", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("uq_messages_client_request_id"), "messages", type_="unique"
    )
    op.drop_column("messages", "client_request_id")
    op.drop_index("ix_messages_operator_id", table_name="messages")
    op.drop_column("messages", "operator_id")
    op.drop_constraint(
        op.f("fk_conversations_assigned_operator_id_ops_users"),
        "conversations",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_conversations_assigned_operator_id"), table_name="conversations"
    )
    op.drop_column("conversations", "control_version")
    op.drop_column("conversations", "assigned_operator_id")
    op.drop_index(op.f("ix_ops_sessions_operator_id"), table_name="ops_sessions")
    op.drop_index(op.f("ix_ops_sessions_expires_at"), table_name="ops_sessions")
    op.drop_table("ops_sessions")
    op.drop_table("ops_login_limits")
