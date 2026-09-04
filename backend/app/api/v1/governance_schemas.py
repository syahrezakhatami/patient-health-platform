from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.governance.domain.enums import (
    DeploymentGateState,
    DeploymentGateType,
    FeatureActivationState,
    ProviderCapabilityState,
)
from app.modules.governance.domain.policy_schema import (
    GovernancePolicyDocumentV1,
    GovernancePolicyDocumentV2,
)

PolicyDocumentInput = Annotated[
    GovernancePolicyDocumentV1 | GovernancePolicyDocumentV2,
    Field(discriminator="schema_version"),
]


class CreateProfileVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_document: PolicyDocumentInput
    effective_at: datetime
    reason: str = Field(min_length=1, max_length=2000)


class PublishProfileVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecordApprovalEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_id: str = Field(min_length=1, max_length=128)
    provider_feature_version: str = Field(min_length=1, max_length=64)
    approval_type: str = Field(min_length=1, max_length=128)
    scope: str = Field(min_length=1, max_length=128)
    decision_by_name: str = Field(min_length=1, max_length=255)
    approval_date: date
    artifact_reference: str | None = Field(default=None, max_length=512)
    approver_role_category: str | None = Field(default=None, max_length=128)
    expires_at: datetime | None = None


class FeatureActivationTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_state: FeatureActivationState
    expected_row_version: int | None = Field(default=None, ge=1)


class DeploymentGateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_state: DeploymentGateState
    expected_row_version: int | None = Field(default=None, ge=1)


class ProviderCapabilityTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_state: ProviderCapabilityState
    expected_row_version: int = Field(ge=1)


class DeploymentGatePathParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_type: DeploymentGateType
