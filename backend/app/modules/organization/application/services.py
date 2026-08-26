from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.audit.application.ports import AuditSink
from app.modules.audit.domain.events import AuditEvent
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.catalog import Permission
from app.modules.iam.domain.models import Principal
from app.modules.organization.domain.enums import (
    FacilityStatus,
    FacilityType,
    OrganizationStatus,
    OrganizationType,
)
from app.modules.organization.domain.models import Facility, Organization, OrganizationIdentifier
from app.modules.organization.infrastructure.models import (
    FacilityModel,
    OrganizationIdentifierModel,
    OrganizationModel,
)
from app.modules.organization.infrastructure.repositories import OrganizationRepository
from app.shared.enums import AuditResult
from app.shared.types.ids import new_id


def normalize_organization_identifier(system: str, value: str) -> str:
    system_key = system.strip()
    raw = value.strip()
    if system_key in {"org.code", "facility.code"}:
        return raw.upper()
    return raw


class OrganizationService:
    def __init__(
        self,
        session: AsyncSession,
        pdp: PolicyDecisionPoint,
        audit: AuditSink,
    ) -> None:
        self._session = session
        self._pdp = pdp
        self._audit = audit
        self._orgs = OrganizationRepository(session)

    async def create_organization(
        self,
        principal: Principal | None,
        *,
        name: str,
        code: str,
        organization_type: OrganizationType,
        actor_organization_id: UUID | None,
        correlation_id: str | None,
    ) -> Organization:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.ORG_ORGANIZATION_CREATE,
            resource_type="Organization",
            organization_id=actor_organization_id,
            purpose="organization_administration",
            correlation_id=correlation_id,
        )
        model = OrganizationModel(
            id=new_id(),
            name=name.strip(),
            code=code.strip().upper(),
            organization_type=organization_type.value,
            status=OrganizationStatus.ACTIVE,
        )
        try:
            await self._orgs.add_organization(model)
        except IntegrityError as exc:
            raise ConflictError("Organization code already exists") from exc
        organization = Organization(
            id=model.id,
            name=model.name,
            code=model.code,
            organization_type=organization_type,
            status=OrganizationStatus.ACTIVE,
        )
        await self._audit.record(
            AuditEvent(
                action="ORGANIZATION_CREATED",
                resource_type="Organization",
                result=AuditResult.SUCCESS,
                actor_id=None if principal is None else principal.user.id,
                organization_id=organization.id,
                resource_id=organization.id,
                purpose="organization_administration",
                correlation_id=correlation_id,
            )
        )
        return organization

    async def get_organization(
        self,
        principal: Principal | None,
        organization_id: UUID,
        *,
        actor_organization_id: UUID | None,
        correlation_id: str | None,
    ) -> Organization:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.ORG_ORGANIZATION_READ,
            resource_type="Organization",
            organization_id=actor_organization_id or organization_id,
            purpose="organization_administration",
            correlation_id=correlation_id,
        )
        organization = await self._orgs.get_organization(organization_id)
        if organization is None:
            raise NotFoundError("Organization not found")
        return organization

    async def create_facility(
        self,
        principal: Principal | None,
        *,
        organization_id: UUID,
        name: str,
        code: str,
        facility_type: FacilityType,
        address_text: str | None,
        correlation_id: str | None,
    ) -> Facility:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.ORG_FACILITY_CREATE,
            resource_type="Facility",
            organization_id=organization_id,
            purpose="organization_administration",
            correlation_id=correlation_id,
        )
        if await self._orgs.get_organization(organization_id) is None:
            raise NotFoundError("Organization not found")
        model = FacilityModel(
            id=new_id(),
            organization_id=organization_id,
            name=name.strip(),
            code=code.strip().upper(),
            facility_type=facility_type.value,
            status=FacilityStatus.ACTIVE,
            address_text=None if address_text is None else address_text.strip(),
        )
        try:
            await self._orgs.add_facility(model)
        except IntegrityError as exc:
            raise ConflictError("Facility code already exists in this organization") from exc
        facility = Facility(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            code=model.code,
            facility_type=facility_type,
            status=FacilityStatus.ACTIVE,
            address_text=model.address_text,
        )
        await self._audit.record(
            AuditEvent(
                action="FACILITY_CREATED",
                resource_type="Facility",
                result=AuditResult.SUCCESS,
                actor_id=None if principal is None else principal.user.id,
                organization_id=organization_id,
                facility_id=facility.id,
                resource_id=facility.id,
                purpose="organization_administration",
                correlation_id=correlation_id,
            )
        )
        return facility

    async def add_identifier(
        self,
        principal: Principal | None,
        *,
        organization_id: UUID,
        identifier_system: str,
        identifier_value: str,
        correlation_id: str | None,
    ) -> OrganizationIdentifier:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.ORG_IDENTIFIER_MANAGE,
            resource_type="OrganizationIdentifier",
            organization_id=organization_id,
            purpose="organization_administration",
            correlation_id=correlation_id,
        )
        if await self._orgs.get_organization(organization_id) is None:
            raise NotFoundError("Organization not found")
        normalized = normalize_organization_identifier(identifier_system, identifier_value)
        model = OrganizationIdentifierModel(
            id=new_id(),
            organization_id=organization_id,
            identifier_system=identifier_system.strip(),
            identifier_value=identifier_value.strip(),
            normalized_value=normalized,
        )
        try:
            await self._orgs.add_identifier(model)
        except IntegrityError as exc:
            raise ConflictError("Organization identifier already exists") from exc
        return OrganizationIdentifier(
            id=model.id,
            organization_id=model.organization_id,
            identifier_system=model.identifier_system,
            identifier_value=model.identifier_value,
            normalized_value=model.normalized_value,
        )
