"""Add nullable webhook timestamp and recovery lease; preserve existing messages."""

import sqlalchemy as sa
from alembic import op

revision = "7d2f6419bc30"
down_revision = "078eb21553bb"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("messages", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("messages", sa.Column("processing_token", sa.UUID(), nullable=True))
    op.add_column(
        "messages", sa.Column("processing_expires_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    op.drop_column("messages", "processing_expires_at")
    op.drop_column("messages", "processing_token")
    op.drop_column("messages", "received_at")
