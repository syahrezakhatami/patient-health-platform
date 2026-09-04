from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ManualVitalMeasurementOptionResponse(BaseModel):
    measurement_key: str
    display_unit: str
    canonical_concept: str


class ManualVitalsWriteContextResponse(BaseModel):
    available: bool
    catalog_version: str | None
    feature_version: str | None
    measurements: list[ManualVitalMeasurementOptionResponse]


class CreateManualVitalMeasurementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_patient_identity_id: UUID
    encounter_id: UUID
    measurement_key: str = Field(min_length=1, max_length=64)
    value: str | int
    effective_at: datetime
