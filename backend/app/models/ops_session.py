"""Only session digests are persisted; raw cookies never reach PostgreSQL."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt


class OpsSession(CreatedAt, Base):
    __tablename__ = "ops_sessions"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    operator_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_users.id", ondelete="RESTRICT"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OpsLoginLimit(Base):
    __tablename__ = "ops_login_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
