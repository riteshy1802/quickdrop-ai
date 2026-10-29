"""Add durable authorization evidence and fenced worker ownership."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "20af73f418ab"
down_revision = "7d2f6419bc30"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payment_intents", sa.Column("authorization", postgresql.JSONB(), nullable=True))
    op.add_column("payment_intents", sa.Column("processing_token", sa.UUID(), nullable=True))
    op.add_column("payment_intents", sa.Column("post_started_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("payment_intents", "post_started_at")
    op.drop_column("payment_intents", "processing_token")
    op.drop_column("payment_intents", "authorization")
