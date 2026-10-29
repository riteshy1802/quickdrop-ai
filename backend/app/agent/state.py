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
    """Untrusted request understanding and general education, never financial authority."""

    model_config = ConfigDict(extra="forbid")
    intent: Literal["complaint", "followup", "status", "help", "other", "unsafe"]
    language: Literal["en", "hi", "hinglish"]
    claims: list[Complaint] = Field(default_factory=list, max_length=6)
    details_unavailable: bool = Field(
        default=False,
        description=(
            "True when the rider cannot supply the pending requested details; not a new claim."
        ),
    )
    clarification_answer: str = Field(
        default="",
        max_length=600,
        description=(
            "Natural acknowledgment and one helpful question for missing scope. "
            "Use pending_clarification and the latest reply; no financial outcome claims."
        ),
    )
    mentioned_amounts: list[str] = Field(default_factory=list, max_length=6)
    help_topic: Literal[
        "general", "fare", "surge", "incentive", "penalty", "window", "approval", "payment"
    ] = "general"
    help_answer: str = Field(default="", max_length=1200)
    simplify: bool = False
    correction: bool = False
    records_disputed: bool = False


class AgentState(TypedDict, total=False):
    rider_id: str
    conversation_id: UUID
    message_id: UUID
    text: str
    received_at: datetime
    reference_time: datetime
    history: list[dict]
    context: dict
    saved: dict | None
    extraction: Extraction
    missing: list[str]
    outcomes: list[dict]
    decision: str
    reply: str
    error: str
