from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UpdatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.dispute import Dispute


class PaymentIntent(UUIDPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "payment_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["dispute_id", "rider_id"],
            ["disputes.id", "disputes.rider_id"],
            name="fk_payment_intents_dispute_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "amount > 0 AND amount < 'Infinity'::numeric AND amount = trunc(amount)",
            name="positive_whole_amount",
        ),
        CheckConstraint(
            "status IN "
            "('PENDING','AWAITING_APPROVAL','PROCESSING','UNKNOWN','SUCCEEDED',"
            "'FAILED','NEEDS_REVIEW')",
            name="status",
        ),
        CheckConstraint("payment_type IN ('AUTO','OPS_APPROVED')", name="payment_type"),
        CheckConstraint("payment_type != 'AUTO' OR amount <= 200", name="auto_amount_limit"),
        CheckConstraint(
            "(payment_type = 'AUTO' AND auto_pay_date IS NOT NULL) OR (payment_type = "
            "'OPS_APPROVED' AND auto_pay_date IS NULL)",
            name="auto_date",
        ),
        CheckConstraint("retry_count >= 0", name="retry_count"),
        # Deliberately includes FAILED/UNKNOWN and every other status: reservations are retained.
        Index(
            "uq_payment_intents_auto_rider_day",
            "rider_id",
            "auto_pay_date",
            unique=True,
            postgresql_where=text("payment_type = 'AUTO'"),
        ),
        Index("ix_payment_intents_dispute_owner", "dispute_id", "rider_id"),
        Index("ix_payment_intents_status_retry", "status", "next_retry_at"),
        Index("ix_payment_intents_lease", "lease_expires_at"),
    )
    dispute_id: Mapped[UUID] = mapped_column(nullable=False)
    rider_id: Mapped[str] = mapped_column(
        ForeignKey("riders.rider_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING", server_default="PENDING"
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    payment_type: Mapped[str] = mapped_column(String(16), nullable=False)
    auto_pay_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    provider_payout_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dispute: Mapped[Dispute] = relationship(back_populates="payment_intents", lazy="raise")
