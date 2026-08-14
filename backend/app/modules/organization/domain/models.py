from dataclasses import dataclass
from uuid import UUID

from app.modules.organization.domain.enums import (
    FacilityStatus,
    FacilityType,
    OrganizationStatus,
    OrganizationType,
)


@dataclass(frozen=True, slots=True)
class Organization:
    id: UUID
    name: str
    code: str
    organization_type: OrganizationType
    status: OrganizationStatus


@dataclass(frozen=True, slots=True)
class Facility:
    id: UUID
    organization_id: UUID
    name: str
    code: str
    facility_type: FacilityType
    status: FacilityStatus
    address_text: str | None


@dataclass(frozen=True, slots=True)
class OrganizationIdentifier:
    id: UUID
    organization_id: UUID
    identifier_system: str
    identifier_value: str
    normalized_value: str
