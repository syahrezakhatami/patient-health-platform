from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.modules.governance.domain.enums import (
    ApprovalEvidenceStatus,
    DeploymentGateState,
    DeploymentGateType,
    FeatureActivationState,
    GovernanceDenialReason,
    ProfileVersionStatus,
    ProviderCapabilityState,
)
from app.modules.governance.domain.policy_schema import GovernancePolicyDocumentV1


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    id: UUID
    feature_id: str
    feature_version: str
    frozen_release_tag: str | None
    provider_state: ProviderCapabilityState
    governance_required: bool
    row_version: int


@dataclass(frozen=True, slots=True)
class GovernanceProfile:
    id: UUID
    organization_id: UUID
    active_published_version_id: UUID | None


@dataclass(frozen=True, slots=True)
class GovernanceProfileVersion:
    id: UUID
    profile_id: UUID
    organization_id: UUID
    version_number: int
    schema_version: int
    policy_document: GovernancePolicyDocumentV1
    status: ProfileVersionStatus
    effective_at: datetime
    changed_by: UUID
    changed_at: datetime
    reason: str
    previous_version_id: UUID | None


@dataclass(frozen=True, slots=True)
class FeatureActivation:
    id: UUID
    organization_id: UUID
    provider_capability_id: UUID
    feature_id: str
    activation_state: FeatureActivationState
    row_version: int


@dataclass(frozen=True, slots=True)
class DeploymentGate:
    id: UUID
    organization_id: UUID
    gate_type: DeploymentGateType
    gate_state: DeploymentGateState
    row_version: int


@dataclass(frozen=True, slots=True)
class ApprovalEvidence:
    id: UUID
    organization_id: UUID
    provider_capability_id: UUID | None
    feature_id: str
    provider_feature_version: str
    governance_profile_version_id: UUID | None
    approval_type: str
    scope: str
    decision_by_name: str
    recorded_by_user_id: UUID
    approval_date: date
    artifact_reference: str | None
    approver_role_category: str | None
    expires_at: datetime | None
    status: ApprovalEvidenceStatus
    supersedes_evidence_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GovernanceResolution:
    registered: bool
    available: bool
    denial_reason: GovernanceDenialReason | None
    feature_id: str | None = None
    feature_version: str | None = None
