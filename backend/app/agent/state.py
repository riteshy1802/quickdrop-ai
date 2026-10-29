from datetime import datetime
from typing import Literal, TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Complaint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["SURGE", "PAYOUT", "INCENTIVE", "PENALTY", "RECORD_DISPUTE"]
    trip_ids: list[str] = Field(default_factory=list, max_length=20)
    date_tokens: list[str] = Field(default_factory=list, max_length=7)


class Extraction(BaseModel):
    """Untrusted language understanding only. No identity or payment authorization fields."""

    model_config = ConfigDict(extra="forbid")
    intent: Literal["complaint", "followup", "status", "other", "unsafe"]
    language: Literal["en", "hi", "hinglish"]
    claims: list[Complaint] = Field(default_factory=list, max_length=6)
    mentioned_amounts: list[str] = Field(default_factory=list, max_length=6)
    correction: bool = False
    records_disputed: bool = False


class AgentState(TypedDict, total=False):
    rider_id: str
    conversation_id: UUID
    message_id: UUID
    text: str
    received_at: datetime
    history: list[dict]
    context: dict
    saved: dict | None
    extraction: Extraction
    missing: list[str]
    outcomes: list[dict]
    decision: str
    reply: str
    error: str
