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


_PLATFORM_SCOPE = "iam.platform"


@dataclass(frozen=True, slots=True)
class Principal:
    user: User
    memberships: tuple[OrganizationMembership, ...]
    permission_codes: frozenset[str]
    organization_ids: frozenset[UUID]
    facility_ids: frozenset[UUID]
    role_codes: frozenset[str]
    permissions_by_role_id: dict[UUID, frozenset[str]]

    @property
    def has_platform_scope(self) -> bool:
        return _PLATFORM_SCOPE in self.permission_codes

    def for_organization(self, organization_id: UUID) -> "Principal":
        """Project tenant memberships, permissions, and facilities for one org.

        Platform memberships (``organization_id is None``) stay on the principal
        so ``iam.platform`` PHI deny and frozen platform administration remain
        intact. They are not rewritten as a hospital membership. Re-applying
        this projection is idempotent for the same organization.
        """
        tenant = tuple(item for item in self.memberships if item.organization_id == organization_id)
        platform = tuple(item for item in self.memberships if item.organization_id is None)
        kept = (*tenant, *platform)
        parts = [self.permissions_by_role_id.get(item.role_id, frozenset()) for item in kept]
        permission_codes = frozenset().union(*parts) if parts else frozenset()
        if self.has_platform_scope and not platform:
            permission_codes = permission_codes | {_PLATFORM_SCOPE}
        org_wide = any(item.facility_id is None for item in tenant)
        if not tenant or org_wide:
            facility_ids: frozenset[UUID] = frozenset()
        else:
            facility_ids = frozenset(
                item.facility_id for item in tenant if item.facility_id is not None
            )
        return Principal(
            user=self.user,
            memberships=kept,
            permission_codes=permission_codes,
            organization_ids=frozenset({organization_id}) if tenant else frozenset(),
            facility_ids=facility_ids,
            role_codes=frozenset(item.role_code for item in kept),
            permissions_by_role_id={
                item.role_id: self.permissions_by_role_id.get(item.role_id, frozenset())
                for item in kept
            },
        )
