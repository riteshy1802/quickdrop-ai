from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

Classification = Literal["VALID", "CORRECTED", "REQUIRES_REVIEW", "INVALID"]


class DataQualityTransformation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rule_id: str
    source_file: str
    source_id: str
    field: str
    original_value: str
    normalized_value: str
    reason: str


class DataQualityIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    code: str
    source_id: str
    classification: Classification
    field: str
    observed_value: str
    effective_value: str | None = None
    reason: str


class TripQuality(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    classification: Classification
    service_date: date
    original_distance: str
    effective_distance: str | None
    transformations: tuple[DataQualityTransformation, ...] = ()
    issues: tuple[DataQualityIssue, ...] = ()
