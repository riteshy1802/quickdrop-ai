from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.ops_queue import OpsQueue


class OpsUser(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "ops_users"
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    assigned_items: Mapped[list[OpsQueue]] = relationship(back_populates="assignee", lazy="raise")
    __table_args__ = (Index("uq_ops_users_email_lower", func.lower(email), unique=True),)
