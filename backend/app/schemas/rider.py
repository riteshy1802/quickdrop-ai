from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class RiderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rider_id: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    joined_on: date
