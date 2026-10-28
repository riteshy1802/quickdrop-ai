from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UpdatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.agent_trace import AgentTrace
    from app.models.dispute import Dispute
    from app.models.message import Message
    from app.models.rider import Rider


class Conversation(UUIDPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("handling_mode IN ('AI','HUMAN')", name="handling_mode"),
        CheckConstraint(
            "status IN "
            "('OPEN','AWAITING_INFORMATION','AWAITING_APPROVAL','ESCALATED',"
            "'HUMAN_HANDLING','PAYMENT_PENDING','RESOLVED')",
            name="status",
        ),
        CheckConstraint("jsonb_typeof(context) = 'object'", name="context_object"),
        UniqueConstraint("id", "rider_id", name="uq_conversations_id_rider"),
        Index("ix_conversations_rider_updated", "rider_id", "updated_at"),
        Index("ix_conversations_status_updated", "status", "updated_at"),
    )
    rider_id: Mapped[str] = mapped_column(
        ForeignKey("riders.rider_id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="OPEN", server_default="OPEN"
    )
    handling_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="AI", server_default="AI"
    )
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    rider: Mapped[Rider] = relationship(back_populates="conversations", lazy="raise")
    messages: Mapped[list[Message]] = relationship(back_populates="conversation", lazy="raise")
    disputes: Mapped[list[Dispute]] = relationship(back_populates="conversation", lazy="raise")
    agent_traces: Mapped[list[AgentTrace]] = relationship(
        back_populates="conversation", lazy="raise"
    )
