from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class Message(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("sender_type IN ('RIDER','AI','OPS')", name="sender_type"),
        CheckConstraint("NOT is_internal OR sender_type = 'OPS'", name="internal_ops_only"),
        CheckConstraint("message_id IS NULL OR sender_type = 'RIDER'", name="webhook_sender"),
        CheckConstraint(
            "processing_status IS NULL OR processing_status IN "
            "('RECEIVED','PROCESSING','COMPLETED','FAILED')",
            name="processing_status",
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at", "id"),
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False
    )
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    sender_type: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    processing_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_token: Mapped[UUID | None] = mapped_column(nullable=True)
    processing_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    webhook_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation: Mapped[Conversation] = relationship(back_populates="messages", lazy="raise")
