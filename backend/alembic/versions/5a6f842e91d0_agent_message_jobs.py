"""Durable agent continuation metadata on the existing messages outbox."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op
revision = "5a6f842e91d0"
down_revision = "20af73f418ab"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("messages", sa.Column("agent_state", postgresql.JSONB(), nullable=True))
    op.add_column("messages", sa.Column("agent_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("messages", sa.Column("next_processing_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_messages_agent_due", "messages", ["processing_status", "next_processing_at", "processing_expires_at"])


def downgrade():
    op.drop_index("ix_messages_agent_due", table_name="messages")
    op.drop_column("messages", "next_processing_at")
    op.drop_column("messages", "agent_attempts")
    op.drop_column("messages", "agent_state")
