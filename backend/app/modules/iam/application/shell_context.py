from collections import defaultdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.modules.audit.application.ports import AuditSink
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.purpose import Purpose
from app.modules.iam.application.shell_schemas import (
    AccessibleFacilitiesResponse,
    AccessibleFacilityDTO,
    AccessibleOrganizationDTO,
    FacilityScopeKind,
    StaffContextResponse,
    StaffOrganizationsResponse,
    StaffSessionUserDTO,
)
from app.modules.iam.domain.models import OrganizationMembership, Principal
from app.modules.organization.domain.models import Facility, Organization
from app.modules.organization.infrastructure.repositories import OrganizationRepository


def tenant_memberships(principal: Principal) -> tuple[OrganizationMembership, ...]:
    return tuple(item for item in principal.memberships if item.organization_id is not None)


def tenant_role_codes(principal: Principal) -> list[str]:
    return sorted({item.role_code for item in tenant_memberships(principal)})


def tenant_permission_codes(principal: Principal) -> list[str]:
    parts = [
        principal.permissions_by_role_id.get(item.role_id, frozenset())
        for item in tenant_memberships(principal)
    ]
    codes = frozenset().union(*parts) if parts else frozenset()
    return sorted(codes)


def facility_scope_kind(principal: Principal) -> FacilityScopeKind:
    tenant = tenant_memberships(principal)
    if any(item.facility_id is None for item in tenant):
        return FacilityScopeKind.ALL_IN_ORGANIZATION
    return FacilityScopeKind.EXPLICIT


def explicit_facility_ids(principal: Principal) -> frozenset[UUID]:
    return frozenset(
        item.facility_id for item in tenant_memberships(principal) if item.facility_id is not None
    )


def work_facility_required(principal: Principal) -> bool:
    """UX hint only. Not an authorization decision."""
    return facility_scope_kind(principal) is FacilityScopeKind.EXPLICIT and bool(
        explicit_facility_ids(principal)
    )


class ShellContextService:
    def __init__(self, session: AsyncSession, pdp: PolicyDecisionPoint, audit: AuditSink) -> None:
        self._session = session
        self._pdp = pdp
        self._audit = audit
        self._orgs = OrganizationRepository(session)

    async def list_organizations(self, principal: Principal | None) -> StaffOrganizationsResponse:
        if principal is None:
            return StaffOrganizationsResponse(provisioned=False)
        grouped: dict[UUID, set[str]] = defaultdict(set)
        for item in tenant_memberships(principal):
            if item.organization_id is not None:
                grouped[item.organization_id].add(item.role_code)
        organizations = await self._orgs.list_organizations_by_ids(tuple(grouped))
        dtos = [
            AccessibleOrganizationDTO(
                organization_id=organization.id,
                name=organization.name,
                code=organization.code,
                organization_type=organization.organization_type.value,
                status=organization.status.value,
                role_codes=sorted(grouped[organization.id]),
            )
            for organization in organizations
        ]
        dtos.sort(key=lambda item: (item.name.lower(), item.code, str(item.organization_id)))
        return StaffOrganizationsResponse(
            provisioned=True,
            user=_user_dto(principal),
            organizations=dtos,
        )

    async def get_context(
        self, principal: Principal | None, organization_id: UUID
    ) -> StaffContextResponse:
        scoped = _require_tenant(principal, organization_id)
        organization = await self._organization(organization_id)
        scope = facility_scope_kind(scoped)
        role_codes = tenant_role_codes(scoped)
        return StaffContextResponse(
            provisioned=True,
            user=_user_dto(scoped),
            organization=AccessibleOrganizationDTO(
                organization_id=organization.id,
                name=organization.name,
                code=organization.code,
                organization_type=organization.organization_type.value,
                status=organization.status.value,
                role_codes=role_codes,
            ),
            role_codes=role_codes,
            effective_permissions=tenant_permission_codes(scoped),
            facility_scope=scope,
            work_facility_required=work_facility_required(scoped),
        )

    async def list_accessible_facilities(
        self,
        principal: Principal | None,
        *,
        organization_id: UUID,
        header_organization_id: UUID,
        correlation_id: str | None,
    ) -> AccessibleFacilitiesResponse:
        if header_organization_id != organization_id:
            raise NotFoundError("Resource not found")
        scoped = _require_tenant(principal, organization_id)
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=scoped,
            action=Permission.ORG_FACILITY_READ,
            resource_type="Facility",
            organization_id=organization_id,
            purpose=Purpose.ADMINISTRATION.value,
            correlation_id=correlation_id,
        )
        scope = facility_scope_kind(scoped)
        if scope is FacilityScopeKind.ALL_IN_ORGANIZATION:
            facilities = await self._orgs.list_facilities_for_shell(organization_id)
        else:
            facilities = await self._orgs.list_facilities_for_shell(
                organization_id, facility_ids=explicit_facility_ids(scoped)
            )
        return AccessibleFacilitiesResponse(
            organization_id=organization_id,
            facility_scope=scope,
            facilities=[_facility_dto(item) for item in facilities],
        )

    async def _organization(self, organization_id: UUID) -> Organization:
        organization = await self._orgs.get_organization(organization_id)
        if organization is None:
            raise NotFoundError("Resource not found")
        return organization


def _require_tenant(principal: Principal | None, organization_id: UUID) -> Principal:
    if principal is None:
        raise ForbiddenError("User is not provisioned")
    scoped = principal.for_organization(organization_id)
    if not tenant_memberships(scoped):
        raise NotFoundError("Resource not found")
    return scoped


def _user_dto(principal: Principal) -> StaffSessionUserDTO:
    return StaffSessionUserDTO(
        id=principal.user.id,
        subject=principal.user.subject,
        display_name=principal.user.display_name,
    )


def _facility_dto(facility: Facility) -> AccessibleFacilityDTO:
    return AccessibleFacilityDTO(
        id=facility.id,
        name=facility.name,
        code=facility.code,
        facility_type=facility.facility_type.value,
        status=facility.status.value,
    )
