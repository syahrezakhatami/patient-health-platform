from typing import Literal

from app.modules.governance.domain.enums import PolicyEffect
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EncounterStatusPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planned: PolicyEffect = PolicyEffect.DENY
    finished: PolicyEffect = PolicyEffect.DENY


class BackdatingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool = False
    reason_required: bool = True
    max_past_offset: str | None = None


class LateDocumentationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finished_encounter_write_allowed: bool = False
    reason_required: bool = True
    secondary_approval_required: bool = False


class CorrectionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_initiator_permissions: list[str] = Field(default_factory=list)
    reason_required: bool = True
    secondary_approval_required: bool = False


class GovernancePolicyDocumentV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    encounter_status_policy: EncounterStatusPolicy = Field(default_factory=EncounterStatusPolicy)
    backdating_policy: BackdatingPolicy = Field(default_factory=BackdatingPolicy)
    late_documentation_policy: LateDocumentationPolicy = Field(
        default_factory=LateDocumentationPolicy
    )
    correction_policy: CorrectionPolicy = Field(default_factory=CorrectionPolicy)


MANUAL_VITALS_POLICY_CATALOG_VERSION = "manual-vitals-mvp-v1"
_MANUAL_VITALS_MEASUREMENT_KEYS = frozenset(
    {
        "heart_rate",
        "respiratory_rate",
        "body_temperature",
        "body_weight",
        "body_height",
    }
)


class ManualVitalSignsPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_version: str = Field(min_length=1, max_length=64)
    approved_measurements: list[str] = Field(min_length=1)

    @field_validator("catalog_version")
    @classmethod
    def validate_catalog_version(cls, value: str) -> str:
        if value != MANUAL_VITALS_POLICY_CATALOG_VERSION:
            raise ValueError("unsupported manual vitals catalog version")
        return value

    @field_validator("approved_measurements")
    @classmethod
    def validate_unique_measurements(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("approved_measurements must be unique")
        unknown = [item for item in value if item not in _MANUAL_VITALS_MEASUREMENT_KEYS]
        if unknown:
            raise ValueError(f"unknown approved measurement: {unknown[0]}")
        return value


class GovernancePolicyDocumentV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    encounter_status_policy: EncounterStatusPolicy = Field(default_factory=EncounterStatusPolicy)
    backdating_policy: BackdatingPolicy = Field(default_factory=BackdatingPolicy)
    late_documentation_policy: LateDocumentationPolicy = Field(
        default_factory=LateDocumentationPolicy
    )
    correction_policy: CorrectionPolicy = Field(default_factory=CorrectionPolicy)
    manual_vital_signs: ManualVitalSignsPolicy


GovernancePolicyDocument = GovernancePolicyDocumentV1 | GovernancePolicyDocumentV2


def parse_policy_document(raw: dict[str, object]) -> GovernancePolicyDocument:
    version = raw.get("schema_version", 1)
    if version == 1:
        return GovernancePolicyDocumentV1.model_validate(raw)
    if version == 2:
        return GovernancePolicyDocumentV2.model_validate(raw)
    raise ValueError(f"unsupported policy schema version: {version}")
