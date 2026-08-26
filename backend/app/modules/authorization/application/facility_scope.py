from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.authorization.domain.models import AuthorizationDecision
from app.modules.organization.infrastructure.repositories import OrganizationRepository


async def facility_tenant_decision(
    session: AsyncSession,
    *,
    facility_id: UUID | None,
    organization_id: UUID | None,
) -> AuthorizationDecision | None:
    """Enforce facility ∈ organization when a facility is present.

    Empty actor facility lists remain organization-wide in Wave1PolicyPDP.
    This check closes the gap Wave1 cannot close without a database lookup:
    a facility UUID must belong to the request organization.
    ``facility_id is None`` is valid (organization-only scope).
    """
    if facility_id is None:
        return None
    if organization_id is None:
        return AuthorizationDecision(
            allowed=False,
            reason="facility_organization_mismatch",
            policy_reference="pdp.product.facility_tenant",
            obligations=("audit_denial",),
        )
    facility = await OrganizationRepository(session).get_facility(facility_id)
    if facility is None:
        return AuthorizationDecision(
            allowed=False,
            reason="facility_not_found",
            policy_reference="pdp.product.facility_tenant",
            obligations=("audit_denial",),
        )
    if facility.organization_id != organization_id:
        return AuthorizationDecision(
            allowed=False,
            reason="facility_organization_mismatch",
            policy_reference="pdp.product.facility_tenant",
            obligations=("audit_denial",),
        )
    return None
