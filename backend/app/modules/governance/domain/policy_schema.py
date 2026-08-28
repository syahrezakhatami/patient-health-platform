from app.modules.governance.domain.enums import PolicyEffect
from pydantic import BaseModel, ConfigDict, Field


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

    schema_version: int = Field(default=1, ge=1, le=1)
    encounter_status_policy: EncounterStatusPolicy = Field(default_factory=EncounterStatusPolicy)
    backdating_policy: BackdatingPolicy = Field(default_factory=BackdatingPolicy)
    late_documentation_policy: LateDocumentationPolicy = Field(
        default_factory=LateDocumentationPolicy
    )
    correction_policy: CorrectionPolicy = Field(default_factory=CorrectionPolicy)
