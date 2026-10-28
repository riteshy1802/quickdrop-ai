from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.rider import Rider


class PayoutLine(Base):
    """Historical payouts only; new adjustments belong to PaymentIntent."""

    __tablename__ = "payout_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["trip_id", "rider_id"],
            ["trips.trip_id", "trips.rider_id"],
            name="fk_payout_lines_trip_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "line_type IN ('trip','daily_incentive','cancellation_penalty')", name="line_type"
        ),
        CheckConstraint(
            "line_type = 'daily_incentive' OR trip_id IS NOT NULL", name="trip_reference"
        ),
        CheckConstraint(
            "amount > '-Infinity'::numeric AND amount < 'Infinity'::numeric", name="finite_amount"
        ),
        Index("ix_payout_lines_rider_date_type", "rider_id", "payout_date", "line_type"),
        Index("ix_payout_lines_trip_owner", "trip_id", "rider_id"),
    )
    line_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    rider_id: Mapped[str] = mapped_column(
        ForeignKey("riders.rider_id", ondelete="RESTRICT"), nullable=False
    )
    trip_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payout_date: Mapped[date] = mapped_column(Date, nullable=False)
    line_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    rider: Mapped[Rider] = relationship(back_populates="payout_lines", lazy="raise")
