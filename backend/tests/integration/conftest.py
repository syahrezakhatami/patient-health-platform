import os
from collections.abc import AsyncIterator

import pytest
from app.core.config import Settings
from app.db.session import create_session_factory
from app.infra.object_storage import InMemoryObjectStorage
from app.main import create_app
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.infrastructure.jwt_oidc_validator import JwtOidcTokenValidator
from app.modules.iam.infrastructure.models import OrganizationMembershipModel, RoleModel, UserModel
from app.modules.organization.domain.enums import OrganizationStatus, OrganizationType
from app.modules.organization.infrastructure.models import OrganizationModel
from app.shared.types.ids import new_id
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from tests.conftest import TEST_SECRET, mint_token

DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


requires_db = pytest.mark.skipif(
    not DATABASE_URL,
    reason="TEST_DATABASE_URL or DATABASE_URL is required for integration tests",
)


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def db_settings() -> Settings:
    assert DATABASE_URL is not None
    return Settings(
        app_env="test",
        app_debug=False,
        database_url=SecretStr(DATABASE_URL),
        auth_issuer="http://localhost:8080/realms/php-dev",
        auth_audience="php-api",
        auth_dev_hs256_secret=SecretStr(TEST_SECRET),
        cors_allowed_origins="http://localhost:3000",
        rate_limit_per_minute=10000,
        openapi_enabled=True,
    )


@pytest.fixture
async def db_app(db_settings: Settings, db_engine: AsyncEngine):
    return create_app(
        db_settings,
        token_validator=JwtOidcTokenValidator(db_settings),
        object_storage=InMemoryObjectStorage(),
        redis=None,
        engine=db_engine,
        session_factory=create_session_factory(db_engine),
    )


@pytest.fixture
async def db_client(db_app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=db_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class SeededActor:
    def __init__(self, user_id, subject: str, organization_id, token: str) -> None:
        self.user_id = user_id
        self.subject = subject
        self.organization_id = organization_id
        self.token = token

    def headers(self, purpose: str = "registration") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Organization-Id": str(self.organization_id),
            "X-Purpose": purpose,
        }


async def seed_actor(
    engine: AsyncEngine,
    *,
    role_code: str,
    org_code: str | None = None,
    organization_id=None,
) -> SeededActor:
    subject = f"user-{new_id()}"
    user_id = new_id()
    async with engine.begin() as connection:
        if organization_id is None:
            organization_id = new_id()
            await connection.execute(
                OrganizationModel.__table__.insert().values(
                    id=organization_id,
                    name=f"Org {org_code or organization_id.hex[:8]}",
                    code=(org_code or f"ORG{organization_id.hex[:8]}").upper(),
                    organization_type=OrganizationType.HOSPITAL,
                    status=OrganizationStatus.ACTIVE,
                )
            )
        role = (
            await connection.execute(select(RoleModel.id).where(RoleModel.code == role_code))
        ).scalar_one()
        await connection.execute(
            UserModel.__table__.insert().values(
                id=user_id,
                subject=subject,
                display_name=subject,
                status=UserStatus.ACTIVE,
            )
        )
        membership_org = None if role_code == RoleCode.PLATFORM_ADMIN else organization_id
        await connection.execute(
            OrganizationMembershipModel.__table__.insert().values(
                id=new_id(),
                user_id=user_id,
                organization_id=membership_org,
                facility_id=None,
                role_id=role,
                status=MembershipStatus.ACTIVE,
            )
        )
    return SeededActor(user_id, subject, organization_id, mint_token(sub=subject))
