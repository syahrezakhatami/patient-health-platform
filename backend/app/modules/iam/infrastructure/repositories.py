from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.domain.models import OrganizationMembership, Principal, Role, User
from app.modules.iam.infrastructure.models import (
    OrganizationMembershipModel,
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
)


class IamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_by_subject(self, subject: str) -> User | None:
        result = await self._session.execute(select(UserModel).where(UserModel.subject == subject))
        row = result.scalar_one_or_none()
        return _to_user(row) if row is not None else None

    async def get_user(self, user_id: UUID) -> User | None:
        row = await self._session.get(UserModel, user_id)
        return _to_user(row) if row is not None else None

    async def get_role_by_code(self, code: str) -> Role | None:
        result = await self._session.execute(select(RoleModel).where(RoleModel.code == code))
        row = result.scalar_one_or_none()
        return Role(id=row.id, code=row.code, name=row.name) if row is not None else None

    async def add_user(self, user: UserModel) -> UserModel:
        self._session.add(user)
        await self._session.flush()
        return user

    async def add_membership(
        self, membership: OrganizationMembershipModel
    ) -> OrganizationMembershipModel:
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def list_active_memberships(self, user_id: UUID) -> list[OrganizationMembership]:
        result = await self._session.execute(
            select(OrganizationMembershipModel, RoleModel)
            .join(RoleModel, RoleModel.id == OrganizationMembershipModel.role_id)
            .where(
                OrganizationMembershipModel.user_id == user_id,
                OrganizationMembershipModel.status == MembershipStatus.ACTIVE,
            )
        )
        memberships: list[OrganizationMembership] = []
        for membership, role in result.all():
            memberships.append(
                OrganizationMembership(
                    id=membership.id,
                    user_id=membership.user_id,
                    organization_id=membership.organization_id,
                    facility_id=membership.facility_id,
                    role_id=membership.role_id,
                    role_code=role.code,
                    status=MembershipStatus(membership.status),
                )
            )
        return memberships

    async def load_principal(self, subject: str) -> Principal | None:
        user = await self.get_user_by_subject(subject)
        if user is None or user.status is not UserStatus.ACTIVE:
            return None
        memberships = await self.list_active_memberships(user.id)
        role_codes = frozenset(item.role_code for item in memberships)
        permission_codes = await self._permission_codes_for_roles(
            [item.role_id for item in memberships]
        )
        organization_ids = frozenset(
            item.organization_id for item in memberships if item.organization_id is not None
        )
        facility_ids = frozenset(
            item.facility_id for item in memberships if item.facility_id is not None
        )
        return Principal(
            user=user,
            memberships=tuple(memberships),
            permission_codes=permission_codes,
            organization_ids=organization_ids,
            facility_ids=facility_ids,
            role_codes=role_codes,
        )

    async def _permission_codes_for_roles(self, role_ids: list[UUID]) -> frozenset[str]:
        if not role_ids:
            return frozenset()
        result = await self._session.execute(
            select(PermissionModel.code)
            .join(RolePermissionModel, RolePermissionModel.permission_id == PermissionModel.id)
            .where(RolePermissionModel.role_id.in_(role_ids))
        )
        return frozenset(result.scalars().all())


def _to_user(row: UserModel) -> User:
    return User(
        id=row.id,
        subject=row.subject,
        display_name=row.display_name,
        status=UserStatus(row.status),
        created_at=row.created_at,
    )
