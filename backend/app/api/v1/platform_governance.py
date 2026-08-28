from fastapi import APIRouter, Depends

from app.api.v1.deps import (
    CorrelationId,
    CurrentAudit,
    UnscopedPrincipal,
    require_platform_audience,
)
from app.api.v1.governance_schemas import ProviderCapabilityTransitionRequest
from app.core.dependencies import CurrentPDP, DbSession
from app.modules.governance.application.services import GovernanceService

router = APIRouter(
    prefix="/platform/governance",
    tags=["platform-governance"],
    dependencies=[Depends(require_platform_audience)],
)


def _service(session: DbSession, pdp: CurrentPDP, audit: CurrentAudit) -> GovernanceService:
    return GovernanceService(session, pdp, audit)


@router.get("/capabilities")
async def list_provider_capabilities(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: UnscopedPrincipal,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    capabilities = await _service(session, pdp, audit).list_provider_capabilities(
        principal,
        correlation_id=correlation_id,
    )
    return {
        "capabilities": [
            {
                "id": str(item.id),
                "feature_id": item.feature_id,
                "feature_version": item.feature_version,
                "provider_state": item.provider_state.value,
                "governance_required": item.governance_required,
                "row_version": item.row_version,
            }
            for item in capabilities
        ]
    }


@router.post("/capabilities/{feature_id}/transition")
async def transition_provider_capability(
    feature_id: str,
    body: ProviderCapabilityTransitionRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: UnscopedPrincipal,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    capability = await _service(session, pdp, audit).transition_provider_capability(
        principal,
        feature_id,
        target_state=body.target_state,
        expected_row_version=body.expected_row_version,
        correlation_id=correlation_id,
    )
    return {
        "id": str(capability.id),
        "feature_id": capability.feature_id,
        "provider_state": capability.provider_state.value,
        "row_version": capability.row_version,
    }
