from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

TripStatus = Literal["completed", "cancelled_by_customer", "cancelled_by_rider"]


class TripResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trip_id: str = Field(min_length=1, max_length=32)
    rider_id: str = Field(min_length=1, max_length=32)
    started_at: AwareDatetime
    status: TripStatus
    distance_km: Decimal = Field(ge=0, allow_inf_nan=False)
    surge_multiplier: Decimal = Field(gt=0, allow_inf_nan=False)
