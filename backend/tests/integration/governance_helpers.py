from datetime import UTC, datetime
from uuid import UUID

from app.modules.governance.domain.enums import ProviderCapabilityState
from app.modules.governance.infrastructure.models import ProviderCapabilityModel
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.infrastructure.models import (
    OrganizationMembershipModel,
    PermissionModel,
    RoleModel,
    UserModel,
)
from app.modules.organization.domain.enums import OrganizationStatus, OrganizationType
from app.modules.organization.infrastructure.models import OrganizationModel
from app.shared.types.ids import new_id
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.conftest import mint_token
from tests.integration.conftest import SeededActor
from tests.integration.db_privileges import (
    restore_governance_app_dml_privileges as _restore_governance_app_dml_privileges,
)


async def insert_test_provider_capability(
    engine: AsyncEngine,
    *,
    feature_id: str,
    feature_version: str = "1.0.0",
    governance_required: bool = False,
    provider_state: ProviderCapabilityState = ProviderCapabilityState.AVAILABLE,
    frozen_release_tag: str | None = None,
) -> UUID:
    capability_id = new_id()
    async with engine.begin() as connection:
        await connection.execute(
            ProviderCapabilityModel.__table__.insert().values(
                id=capability_id,
                feature_id=feature_id,
                feature_version=feature_version,
                frozen_release_tag=frozen_release_tag,
                provider_state=provider_state.value,
                governance_required=governance_required,
                row_version=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    return capability_id


def governance_headers(
    actor,
    *,
    purpose: str = "governance_administration",
    idempotency_key: str | None = None,
) -> dict[str, str]:
    headers = actor.headers(purpose=purpose)
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def platform_headers(token: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Purpose": "platform_governance",
    }
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


async def seed_governance_actor(
    engine: AsyncEngine,
    *,
    permissions: frozenset[str],
    org_code: str | None = None,
) -> SeededActor:
    """Seed an org member whose role carries only the requested governance permissions."""
    role_code = f"GOV_TEST_{new_id().hex[:8].upper()}"
    subject = f"user-{new_id()}"
    user_id = new_id()
    organization_id = new_id()
    role_id = new_id()
    async with engine.begin() as connection:
        await connection.execute(
            OrganizationModel.__table__.insert().values(
                id=organization_id,
                name=f"Org {org_code or organization_id.hex[:8]}",
                code=(org_code or f"ORG{organization_id.hex[:8]}").upper(),
                organization_type=OrganizationType.HOSPITAL,
                status=OrganizationStatus.ACTIVE,
            )
        )
        await connection.execute(
            RoleModel.__table__.insert().values(
                id=role_id,
                code=role_code,
                name=f"Governance test role {role_code}",
            )
        )
        permission_ids = (
            await connection.execute(
                select(PermissionModel.id).where(PermissionModel.code.in_(tuple(permissions)))
            )
        ).scalars().all()
        for permission_id in permission_ids:
            await connection.execute(
                text(
                    """
                    INSERT INTO role_permissions (id, role_id, permission_id)
                    VALUES (:id, :role_id, :permission_id)
                    """
                ),
                {"id": new_id(), "role_id": role_id, "permission_id": permission_id},
            )
        await connection.execute(
            UserModel.__table__.insert().values(
                id=user_id,
                subject=subject,
                display_name=subject,
                status=UserStatus.ACTIVE,
            )
        )
        await connection.execute(
            OrganizationMembershipModel.__table__.insert().values(
                id=new_id(),
                user_id=user_id,
                organization_id=organization_id,
                facility_id=None,
                role_id=role_id,
                status=MembershipStatus.ACTIVE,
            )
        )
    return SeededActor(user_id, subject, organization_id, mint_token(sub=subject))


async def restore_governance_app_dml_privileges(db_engine) -> None:
    await _restore_governance_app_dml_privileges(db_engine)
