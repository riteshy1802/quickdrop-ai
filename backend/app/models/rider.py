from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.payout_line import PayoutLine
    from app.models.trip import Trip


class Rider(Base):
    __tablename__ = "riders"
    rider_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    joined_on: Mapped[date] = mapped_column(Date, nullable=False)
    trips: Mapped[list[Trip]] = relationship(back_populates="rider", lazy="raise")
    payout_lines: Mapped[list[PayoutLine]] = relationship(back_populates="rider", lazy="raise")
    conversations: Mapped[list[Conversation]] = relationship(back_populates="rider", lazy="raise")
