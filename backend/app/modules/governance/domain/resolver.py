from datetime import UTC, datetime

from app.modules.governance.domain.enums import (
    ApprovalEvidenceStatus,
    DeploymentGateState,
    DeploymentGateType,
    FeatureActivationState,
    GovernanceDenialReason,
    ProviderCapabilityState,
)
from app.modules.governance.domain.models import (
    ApprovalEvidence,
    DeploymentGate,
    FeatureActivation,
    GovernanceResolution,
    ProviderCapability,
)


def resolve_provider_layer(capability: ProviderCapability | None) -> GovernanceResolution:
    if capability is None:
        return GovernanceResolution(
            registered=False,
            available=False,
            denial_reason=GovernanceDenialReason.NOT_REGISTERED,
        )
    if capability.provider_state == ProviderCapabilityState.SUSPENDED:
        return GovernanceResolution(
            registered=True,
            available=False,
            denial_reason=GovernanceDenialReason.DENIED_PROVIDER,
            feature_id=capability.feature_id,
            feature_version=capability.feature_version,
        )
    if capability.provider_state == ProviderCapabilityState.RETIRED:
        return GovernanceResolution(
            registered=True,
            available=False,
            denial_reason=GovernanceDenialReason.DENIED_PROVIDER,
            feature_id=capability.feature_id,
            feature_version=capability.feature_version,
        )
    return GovernanceResolution(
        registered=True,
        available=True,
        denial_reason=None,
        feature_id=capability.feature_id,
        feature_version=capability.feature_version,
    )


def resolve_governance_required_layers(
    *,
    capability: ProviderCapability,
    activation: FeatureActivation | None,
    required_gate_types: frozenset[DeploymentGateType],
    gates: dict[DeploymentGateType, DeploymentGate],
    approval_evidence: list[ApprovalEvidence],
    organization_active: bool,
) -> GovernanceResolution:
    base = resolve_provider_layer(capability)
    if not base.available:
        return base
    if not organization_active:
        return GovernanceResolution(
            registered=True,
            available=False,
            denial_reason=GovernanceDenialReason.DENIED_ENTITLEMENT,
            feature_id=capability.feature_id,
            feature_version=capability.feature_version,
        )
    for gate_type in required_gate_types:
        gate = gates.get(gate_type)
        if gate is None or gate.gate_state in {
            DeploymentGateState.NOT_ASSESSED,
            DeploymentGateState.PENDING,
            DeploymentGateState.EXPIRED,
        }:
            return GovernanceResolution(
                registered=True,
                available=False,
                denial_reason=GovernanceDenialReason.DENIED_DEPLOYMENT_GATE,
                feature_id=capability.feature_id,
                feature_version=capability.feature_version,
            )
    if activation is None or activation.activation_state != FeatureActivationState.ACTIVE:
        return GovernanceResolution(
            registered=True,
            available=False,
            denial_reason=GovernanceDenialReason.DENIED_SITE_ACTIVATION,
            feature_id=capability.feature_id,
            feature_version=capability.feature_version,
        )
    now = datetime.now(UTC)
    has_valid_approval = any(
        evidence.status == ApprovalEvidenceStatus.APPROVED
        and evidence.feature_id == capability.feature_id
        and (evidence.expires_at is None or evidence.expires_at > now)
        for evidence in approval_evidence
    )
    if not has_valid_approval:
        return GovernanceResolution(
            registered=True,
            available=False,
            denial_reason=GovernanceDenialReason.DENIED_SITE_ACTIVATION,
            feature_id=capability.feature_id,
            feature_version=capability.feature_version,
        )
    return GovernanceResolution(
        registered=True,
        available=True,
        denial_reason=None,
        feature_id=capability.feature_id,
        feature_version=capability.feature_version,
    )
