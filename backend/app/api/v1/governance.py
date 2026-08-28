from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.v1.deps import (
    CorrelationId,
    CurrentAudit,
    CurrentPrincipal,
    RequestOrganizationId,
    RequiredIdempotencyKey,
    require_staff_audience,
)
from app.api.v1.governance_schemas import (
    CreateProfileVersionRequest,
    DeploymentGateUpdateRequest,
    FeatureActivationTransitionRequest,
    RecordApprovalEvidenceRequest,
)
from app.core.dependencies import CurrentPDP, DbSession
from app.modules.governance.application.services import GovernanceService
from app.modules.governance.domain.enums import DeploymentGateType

router = APIRouter(
    prefix="/organizations/{organization_id}/governance",
    tags=["governance"],
    dependencies=[Depends(require_staff_audience)],
)


def _service(session: DbSession, pdp: CurrentPDP, audit: CurrentAudit) -> GovernanceService:
    return GovernanceService(session, pdp, audit)


@router.get("/effective-context")
async def get_effective_context(
    organization_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    actor_organization_id: RequestOrganizationId,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    if actor_organization_id != organization_id:
        from app.core.errors import NotFoundError

        raise NotFoundError("Resource not found")
    return await _service(session, pdp, audit).get_effective_context(
        principal,
        organization_id,
        correlation_id=correlation_id,
    )


@router.get("/profile")
async def get_governance_profile(
    organization_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    actor_organization_id: RequestOrganizationId,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    if actor_organization_id != organization_id:
        from app.core.errors import NotFoundError

        raise NotFoundError("Resource not found")
    return await _service(session, pdp, audit).get_management_profile(
        principal,
        organization_id,
        correlation_id=correlation_id,
    )


@router.post("/profile/versions")
async def create_profile_version(
    organization_id: UUID,
    body: CreateProfileVersionRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    actor_organization_id: RequestOrganizationId,
    idempotency_key: RequiredIdempotencyKey,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    if actor_organization_id != organization_id:
        from app.core.errors import NotFoundError

        raise NotFoundError("Resource not found")
    version = await _service(session, pdp, audit).create_profile_version(
        principal,
        organization_id,
        policy_document=body.policy_document,
        effective_at=body.effective_at,
        reason=body.reason,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "status": version.status.value,
        "effective_at": version.effective_at.isoformat(),
    }


@router.post("/profile/versions/{version_id}/publish")
async def publish_profile_version(
    organization_id: UUID,
    version_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    actor_organization_id: RequestOrganizationId,
    idempotency_key: RequiredIdempotencyKey,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    if actor_organization_id != organization_id:
        from app.core.errors import NotFoundError

        raise NotFoundError("Resource not found")
    version = await _service(session, pdp, audit).publish_profile_version(
        principal,
        organization_id,
        version_id,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "status": version.status.value,
        "effective_at": version.effective_at.isoformat(),
    }


@router.post("/approvals")
async def record_approval_evidence(
    organization_id: UUID,
    body: RecordApprovalEvidenceRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    actor_organization_id: RequestOrganizationId,
    idempotency_key: RequiredIdempotencyKey,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    if actor_organization_id != organization_id:
        from app.core.errors import NotFoundError

        raise NotFoundError("Resource not found")
    approval_date = body.approval_date
    evidence = await _service(session, pdp, audit).record_approval_evidence(
        principal,
        organization_id,
        feature_id=body.feature_id,
        provider_feature_version=body.provider_feature_version,
        approval_type=body.approval_type,
        scope=body.scope,
        decision_by_name=body.decision_by_name,
        approval_date=approval_date,
        artifact_reference=body.artifact_reference,
        approver_role_category=body.approver_role_category,
        expires_at=body.expires_at,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    return {
        "id": str(evidence.id),
        "feature_id": evidence.feature_id,
        "status": evidence.status.value,
        "approval_date": evidence.approval_date.isoformat(),
    }


@router.post("/features/{feature_id}/transition")
async def transition_feature_activation(
    organization_id: UUID,
    feature_id: str,
    body: FeatureActivationTransitionRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    actor_organization_id: RequestOrganizationId,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    if actor_organization_id != organization_id:
        from app.core.errors import NotFoundError

        raise NotFoundError("Resource not found")
    activation = await _service(session, pdp, audit).transition_feature_activation(
        principal,
        organization_id,
        feature_id,
        target_state=body.target_state,
        expected_row_version=body.expected_row_version,
        correlation_id=correlation_id,
    )
    return {
        "id": str(activation.id),
        "feature_id": activation.feature_id,
        "activation_state": activation.activation_state.value,
        "row_version": activation.row_version,
    }


@router.put("/deployment-gates/{gate_type}")
async def update_deployment_gate(
    organization_id: UUID,
    gate_type: DeploymentGateType,
    body: DeploymentGateUpdateRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    actor_organization_id: RequestOrganizationId,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    if actor_organization_id != organization_id:
        from app.core.errors import NotFoundError

        raise NotFoundError("Resource not found")
    gate = await _service(session, pdp, audit).update_deployment_gate(
        principal,
        organization_id,
        gate_type,
        gate_state=body.gate_state,
        expected_row_version=body.expected_row_version,
        correlation_id=correlation_id,
    )
    return {
        "id": str(gate.id),
        "gate_type": gate.gate_type.value,
        "gate_state": gate.gate_state.value,
        "row_version": gate.row_version,
    }
