from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

PayoutLineType = Literal["trip", "daily_incentive", "cancellation_penalty"]


class PayoutLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line_id: str = Field(min_length=1, max_length=40)
    rider_id: str = Field(min_length=1, max_length=32)
    trip_id: str | None = Field(default=None, min_length=1, max_length=32)
    payout_date: date
    line_type: PayoutLineType
    amount: Decimal = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def require_trip_reference(self) -> Self:
        if self.line_type != "daily_incentive" and self.trip_id is None:
            raise ValueError("A trip reference is required for this payout line type")
        return self
