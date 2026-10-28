from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.dispute import Dispute
    from app.models.ops_user import OpsUser


class OpsQueue(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "ops_queue"
    __table_args__ = (
        CheckConstraint("type IN ('approval','escalation')", name="type"),
        CheckConstraint(
            "status IN ('PENDING','IN_REVIEW','APPROVED','REJECTED','RESOLVED')", name="status"
        ),
        CheckConstraint(
            "amount IS NULL OR (amount >= 0 AND amount < 'Infinity'::numeric)", name="amount"
        ),
        CheckConstraint("type != 'approval' OR amount IS NOT NULL", name="approval_amount"),
        Index(
            "ix_ops_queue_pending_created",
            "status",
            "created_at",
            postgresql_where=text("status IN ('PENDING','IN_REVIEW')"),
        ),
    )
    dispute_id: Mapped[UUID] = mapped_column(
        ForeignKey("disputes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING", server_default="PENDING"
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric(), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_to: Mapped[UUID | None] = mapped_column(
        ForeignKey("ops_users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispute: Mapped[Dispute] = relationship(back_populates="queue_items", lazy="raise")
    assignee: Mapped[OpsUser | None] = relationship(back_populates="assigned_items", lazy="raise")
