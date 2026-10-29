from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import Base, CreatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.conversation import Conversation

_SENSITIVE = re.compile(
    r"api.?key|authorization|password|secret|credential|cookie|token|private.?key|chain.?of.?thought|hidden.?reasoning",
    re.IGNORECASE,
)


def redact_trace_payload(value: Any) -> Any:
    """Defense in depth for ORM writes; future trace writers must sanitize values too."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SENSITIVE.search(str(key)) else redact_trace_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_trace_payload(item) for item in value]
    return value


class AgentTrace(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "agent_traces"
    __table_args__ = (
        CheckConstraint(
            "type IN ('message_in','tool_call','decision','reply','error')", name="type"
        ),
        Index("ix_agent_traces_conversation_created", "conversation_id", "created_at", "id"),
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    input: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    output: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    conversation: Mapped[Conversation] = relationship(back_populates="agent_traces", lazy="raise")

    @validates("input", "output")
    def sanitize_payload(self, key: str, value: Any) -> Any:
        return redact_trace_payload(value)
