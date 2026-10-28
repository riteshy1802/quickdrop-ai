from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.rider import Rider


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint(
            "status IN ('completed','cancelled_by_customer','cancelled_by_rider')", name="status"
        ),
        CheckConstraint("distance_km >= 0 AND distance_km < 'Infinity'::numeric", name="distance"),
        CheckConstraint(
            "surge_multiplier > 0 AND surge_multiplier < 'Infinity'::numeric", name="surge"
        ),
        UniqueConstraint("trip_id", "rider_id", name="uq_trips_trip_rider"),
        Index("ix_trips_rider_started", "rider_id", "started_at"),
    )
    trip_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    rider_id: Mapped[str] = mapped_column(
        ForeignKey("riders.rider_id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    distance_km: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    surge_multiplier: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    rider: Mapped[Rider] = relationship(back_populates="trips", lazy="raise")
