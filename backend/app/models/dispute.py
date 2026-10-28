from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UpdatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.dispute_item import DisputeItem
    from app.models.ops_queue import OpsQueue
    from app.models.payment_intent import PaymentIntent


class Dispute(UUIDPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "disputes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "rider_id"],
            ["conversations.id", "conversations.rider_id"],
            name="fk_disputes_conversation_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "rider_id", name="uq_disputes_id_rider"),
        CheckConstraint(
            "status IN "
            "('OPEN','INVESTIGATING','AWAITING_INFORMATION','AWAITING_APPROVAL',"
            "'VERIFIED','PAYMENT_PENDING','RESOLVED','REJECTED','ESCALATED')",
            name="status",
        ),
        CheckConstraint(
            "claimed_amount IS NULL OR (claimed_amount >= 0 AND claimed_amount < "
            "'Infinity'::numeric)",
            name="claimed_amount",
        ),
        CheckConstraint(
            "verified_amount IS NULL OR (verified_amount >= 0 AND verified_amount < "
            "'Infinity'::numeric)",
            name="verified_amount",
        ),
        CheckConstraint("jsonb_typeof(details) = 'object'", name="details_object"),
        Index("ix_disputes_conversation_owner", "conversation_id", "rider_id"),
        Index("ix_disputes_rider_created", "rider_id", "created_at"),
    )
    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    rider_id: Mapped[str] = mapped_column(
        ForeignKey("riders.rider_id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="OPEN", server_default="OPEN"
    )
    claimed_amount: Mapped[Decimal | None] = mapped_column(Numeric(), nullable=True)
    verified_amount: Mapped[Decimal | None] = mapped_column(Numeric(), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    conversation: Mapped[Conversation] = relationship(back_populates="disputes", lazy="raise")
    items: Mapped[list[DisputeItem]] = relationship(back_populates="dispute", lazy="raise")
    payment_intents: Mapped[list[PaymentIntent]] = relationship(
        back_populates="dispute", lazy="raise"
    )
    queue_items: Mapped[list[OpsQueue]] = relationship(back_populates="dispute", lazy="raise")
