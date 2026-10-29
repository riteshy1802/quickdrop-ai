from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class IncomingMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(min_length=1, max_length=255)
    rider_id: str = Field(min_length=1, max_length=32)
    text: str = Field(min_length=1, max_length=10000)
    received_at: AwareDatetime

    @field_validator("message_id", "rider_id", "text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must not be blank")
        return value


class MessageReply(BaseModel):
    reply: str
