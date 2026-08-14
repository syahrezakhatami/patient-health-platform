from fastapi import APIRouter

from app.api.v1.deps import (
    CorrelationId,
    CurrentAudit,
    CurrentPrincipal,
    OptionalOrganizationId,
    RequestOrganizationId,
)
from app.api.v1.schemas import AssignMembershipRequest, ProvisionUserRequest
from app.core.dependencies import CurrentPDP, DbSession
from app.modules.iam.application.services import IamService

router = APIRouter(prefix="/iam", tags=["iam"])


def _service(session: DbSession, pdp: CurrentPDP, audit: CurrentAudit) -> IamService:
    return IamService(session, pdp, audit)


@router.post("/users")
async def provision_user(
    body: ProvisionUserRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: OptionalOrganizationId,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    user = await _service(session, pdp, audit).provision_user(
        principal,
        subject=body.subject,
        display_name=body.display_name,
        organization_id=organization_id,
        correlation_id=correlation_id,
    )
    return {
        "id": str(user.id),
        "subject": user.subject,
        "display_name": user.display_name,
        "status": user.status,
    }


@router.get("/users/me")
async def current_user(principal: CurrentPrincipal) -> dict[str, object]:
    if principal is None:
        return {"provisioned": False}
    return {
        "provisioned": True,
        "id": str(principal.user.id),
        "subject": principal.user.subject,
        "display_name": principal.user.display_name,
        "roles": sorted(principal.role_codes),
        "permissions": sorted(principal.permission_codes),
    }


@router.post("/memberships")
async def assign_membership(
    body: AssignMembershipRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    membership = await _service(session, pdp, audit).assign_membership(
        principal,
        user_id=body.user_id,
        organization_id=body.organization_id,
        facility_id=body.facility_id,
        role_code=body.role_code,
        actor_organization_id=organization_id,
        correlation_id=correlation_id,
    )
    return {
        "id": str(membership.id),
        "user_id": str(membership.user_id),
        "organization_id": (
            None if membership.organization_id is None else str(membership.organization_id)
        ),
        "facility_id": None if membership.facility_id is None else str(membership.facility_id),
        "role_code": membership.role_code,
        "status": membership.status,
    }
