from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.v1.deps import (
    CorrelationId,
    CurrentAudit,
    CurrentPrincipal,
    OptionalOrganizationId,
    RequestOrganizationId,
    require_staff_or_platform_audience,
)
from app.api.v1.schemas import (
    CreateFacilityRequest,
    CreateOrganizationRequest,
    OrganizationIdentifierRequest,
)
from app.core.dependencies import CurrentPDP, DbSession
from app.modules.organization.application.services import OrganizationService

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
    dependencies=[Depends(require_staff_or_platform_audience)],
)


def _service(session: DbSession, pdp: CurrentPDP, audit: CurrentAudit) -> OrganizationService:
    return OrganizationService(session, pdp, audit)


@router.post("")
async def create_organization(
    body: CreateOrganizationRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    actor_organization_id: OptionalOrganizationId,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    organization = await _service(session, pdp, audit).create_organization(
        principal,
        name=body.name,
        code=body.code,
        organization_type=body.organization_type,
        actor_organization_id=actor_organization_id,
        correlation_id=correlation_id,
    )
    return {
        "id": str(organization.id),
        "name": organization.name,
        "code": organization.code,
        "organization_type": organization.organization_type,
        "status": organization.status,
    }


@router.get("/{organization_id}")
async def get_organization(
    organization_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    actor_organization_id: RequestOrganizationId,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    organization = await _service(session, pdp, audit).get_organization(
        principal,
        organization_id,
        actor_organization_id=actor_organization_id,
        correlation_id=correlation_id,
    )
    return {
        "id": str(organization.id),
        "name": organization.name,
        "code": organization.code,
        "organization_type": organization.organization_type,
        "status": organization.status,
    }


@router.post("/{organization_id}/facilities")
async def create_facility(
    organization_id: UUID,
    body: CreateFacilityRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    facility = await _service(session, pdp, audit).create_facility(
        principal,
        organization_id=organization_id,
        name=body.name,
        code=body.code,
        facility_type=body.facility_type,
        address_text=body.address_text,
        correlation_id=correlation_id,
    )
    return {
        "id": str(facility.id),
        "organization_id": str(facility.organization_id),
        "name": facility.name,
        "code": facility.code,
        "facility_type": facility.facility_type,
        "status": facility.status,
        "address_text": facility.address_text,
    }


@router.post("/{organization_id}/identifiers")
async def add_organization_identifier(
    organization_id: UUID,
    body: OrganizationIdentifierRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    identifier = await _service(session, pdp, audit).add_identifier(
        principal,
        organization_id=organization_id,
        identifier_system=body.identifier_system,
        identifier_value=body.identifier_value,
        correlation_id=correlation_id,
    )
    return {
        "id": str(identifier.id),
        "organization_id": str(identifier.organization_id),
        "identifier_system": identifier.identifier_system,
        "identifier_value": identifier.identifier_value,
    }
