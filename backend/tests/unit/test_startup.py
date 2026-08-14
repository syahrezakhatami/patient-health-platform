import pytest
from app.infra.object_storage import InMemoryObjectStorage
from app.main import create_app
from app.modules.iam.infrastructure.jwt_oidc_validator import JwtOidcTokenValidator
from httpx import ASGITransport, AsyncClient
from tests.conftest import make_settings

pytestmark = pytest.mark.unit


async def test_application_starts() -> None:
    settings = make_settings()
    app = create_app(
        settings,
        token_validator=JwtOidcTokenValidator(settings),
        object_storage=InMemoryObjectStorage(),
        redis=None,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
