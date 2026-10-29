from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Reason(Action):
    reason: str = Field(min_length=1, max_length=2000)


class Assignment(Action):
    operator_id: UUID | None = None


class HumanMessage(Action):
    text: str = Field(min_length=1, max_length=10000)
    client_request_id: UUID
