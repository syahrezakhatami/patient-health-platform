import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_DEBUG", "false")
os.environ.setdefault("AUTH_DEV_HS256_SECRET", "unit-test-hs256-secret-32b-minimum!!")
os.environ.setdefault("AUTH_ISSUER", "http://localhost:8080/realms/php-dev")
os.environ.setdefault("AUTH_AUDIENCE", "php-api")

from app.core.config import Settings, reset_settings_cache
from app.infra.object_storage import InMemoryObjectStorage
from app.main import create_app
from app.modules.iam.infrastructure.jwt_oidc_validator import JwtOidcTokenValidator

TEST_SECRET = "unit-test-hs256-secret-32b-minimum!!"


def make_settings(**overrides: object) -> Settings:
    reset_settings_cache()
    values: dict[str, object] = {
        "app_env": "test",
        "app_debug": False,
        "auth_issuer": "http://localhost:8080/realms/php-dev",
        "auth_audience": "php-api",
        "auth_dev_hs256_secret": SecretStr(TEST_SECRET),
        "cors_allowed_origins": "http://localhost:3000",
        "max_request_bytes": 1024,
        "rate_limit_per_minute": 10000,
        "openapi_enabled": True,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def mint_token(
    *,
    sub: str = "user-1",
    iss: str = "http://localhost:8080/realms/php-dev",
    aud: str = "php-api",
    exp_delta: timedelta = timedelta(minutes=5),
    secret: str = TEST_SECRET,
    algorithm: str = "HS256",
    extra: dict[str, object] | None = None,
) -> str:
    payload: dict[str, object] = {
        "sub": sub,
        "iss": iss,
        "aud": aud,
        "exp": datetime.now(UTC) + exp_delta,
        "iat": datetime.now(UTC),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm=algorithm)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings):
    return create_app(
        settings,
        token_validator=JwtOidcTokenValidator(settings),
        object_storage=InMemoryObjectStorage(),
        redis=None,
    )


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
