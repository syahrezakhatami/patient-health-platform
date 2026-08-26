from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ShellModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FacilityScopeKind(StrEnum):
    ALL_IN_ORGANIZATION = "ALL_IN_ORGANIZATION"
    EXPLICIT = "EXPLICIT"


class StaffSessionUserDTO(ShellModel):
    id: UUID
    subject: str
    display_name: str


class AccessibleOrganizationDTO(ShellModel):
    organization_id: UUID
    name: str
    code: str
    organization_type: str
    status: str
    role_codes: list[str]


class StaffOrganizationsResponse(ShellModel):
    provisioned: bool
    user: StaffSessionUserDTO | None = None
    organizations: list[AccessibleOrganizationDTO] = Field(default_factory=list)


class AccessibleFacilityDTO(ShellModel):
    id: UUID
    name: str
    code: str
    facility_type: str
    status: str


class StaffContextResponse(ShellModel):
    provisioned: bool
    user: StaffSessionUserDTO
    organization: AccessibleOrganizationDTO
    role_codes: list[str]
    effective_permissions: list[str]
    facility_scope: FacilityScopeKind
    work_facility_required: bool


class AccessibleFacilitiesResponse(ShellModel):
    organization_id: UUID
    facility_scope: FacilityScopeKind
    facilities: list[AccessibleFacilityDTO]
