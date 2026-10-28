from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.dispute import Dispute


class DisputeItem(UUIDPrimaryKey, Base):
    __tablename__ = "dispute_items"
    __table_args__ = (
        CheckConstraint("source_type IN ('trip','incentive','penalty')", name="source_type"),
        CheckConstraint(
            "expected_amount > '-Infinity'::numeric AND expected_amount < "
            "'Infinity'::numeric AND actual_amount > '-Infinity'::numeric AND "
            "actual_amount < 'Infinity'::numeric AND difference > "
            "'-Infinity'::numeric AND difference < 'Infinity'::numeric",
            name="finite_amounts",
        ),
    )
    dispute_id: Mapped[UUID] = mapped_column(
        ForeignKey("disputes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    difference: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    dispute: Mapped[Dispute] = relationship(back_populates="items", lazy="raise")
