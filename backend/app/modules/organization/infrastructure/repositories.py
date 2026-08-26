from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_organization(self, model: OrganizationModel) -> OrganizationModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_facility(self, model: FacilityModel) -> FacilityModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_identifier(
        self, model: OrganizationIdentifierModel
    ) -> OrganizationIdentifierModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_organization(self, organization_id: UUID) -> Organization | None:
        row = await self._session.get(OrganizationModel, organization_id)
        return _to_organization(row) if row is not None else None

    async def get_organization_by_code(self, code: str) -> Organization | None:
        result = await self._session.execute(
            select(OrganizationModel).where(OrganizationModel.code == code)
        )
        row = result.scalar_one_or_none()
        return _to_organization(row) if row is not None else None

    async def get_facility(self, facility_id: UUID) -> Facility | None:
        row = await self._session.get(FacilityModel, facility_id)
        return _to_facility(row) if row is not None else None

    async def list_facilities(self, organization_id: UUID) -> list[Facility]:
        result = await self._session.execute(
            select(FacilityModel).where(FacilityModel.organization_id == organization_id)
        )
        return [_to_facility(row) for row in result.scalars().all()]

    async def list_organizations_by_ids(
        self, organization_ids: tuple[UUID, ...]
    ) -> list[Organization]:
        if not organization_ids:
            return []
        result = await self._session.execute(
            select(OrganizationModel).where(OrganizationModel.id.in_(organization_ids))
        )
        by_id = {row.id: _to_organization(row) for row in result.scalars().all()}
        return [by_id[item_id] for item_id in organization_ids if item_id in by_id]

    async def list_facilities_for_shell(
        self,
        organization_id: UUID,
        *,
        facility_ids: frozenset[UUID] | None = None,
    ) -> list[Facility]:
        stmt = select(FacilityModel).where(
            FacilityModel.organization_id == organization_id,
            FacilityModel.status == FacilityStatus.ACTIVE.value,
        )
        if facility_ids is not None:
            if not facility_ids:
                return []
            stmt = stmt.where(FacilityModel.id.in_(facility_ids))
        stmt = stmt.order_by(FacilityModel.name.asc(), FacilityModel.id.asc())
        result = await self._session.execute(stmt)
        return [_to_facility(row) for row in result.scalars().all()]

    async def list_identifiers(self, organization_id: UUID) -> list[OrganizationIdentifier]:
        result = await self._session.execute(
            select(OrganizationIdentifierModel).where(
                OrganizationIdentifierModel.organization_id == organization_id
            )
        )
        return [
            OrganizationIdentifier(
                id=row.id,
                organization_id=row.organization_id,
                identifier_system=row.identifier_system,
                identifier_value=row.identifier_value,
                normalized_value=row.normalized_value,
            )
            for row in result.scalars().all()
        ]


def _to_organization(row: OrganizationModel) -> Organization:
    return Organization(
        id=row.id,
        name=row.name,
        code=row.code,
        organization_type=OrganizationType(row.organization_type),
        status=OrganizationStatus(row.status),
    )


def _to_facility(row: FacilityModel) -> Facility:
    return Facility(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        code=row.code,
        facility_type=FacilityType(row.facility_type),
        status=FacilityStatus(row.status),
        address_text=row.address_text,
    )
