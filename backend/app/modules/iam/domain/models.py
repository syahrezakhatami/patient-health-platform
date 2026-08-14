from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.iam.domain.enums import MembershipStatus, UserStatus


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    subject: str
    display_name: str
    status: UserStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Role:
    id: UUID
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class OrganizationMembership:
    id: UUID
    user_id: UUID
    organization_id: UUID | None
    facility_id: UUID | None
    role_id: UUID
    role_code: str
    status: MembershipStatus


@dataclass(frozen=True, slots=True)
class Principal:
    user: User
    memberships: tuple[OrganizationMembership, ...]
    permission_codes: frozenset[str]
    organization_ids: frozenset[UUID]
    facility_ids: frozenset[UUID]
    role_codes: frozenset[str]

    @property
    def has_platform_scope(self) -> bool:
        return "iam.platform" in self.permission_codes
