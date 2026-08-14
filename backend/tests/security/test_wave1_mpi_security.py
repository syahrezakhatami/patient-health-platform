import pytest
from app.main import create_app
from tests.conftest import make_settings, mint_token

pytestmark = pytest.mark.security


async def test_unauthenticated_identity_creation_rejected(client) -> None:
    response = await client.post("/api/v1/mpi/identities", json={"identifiers": []})
    assert response.status_code == 401


async def test_patient_name_search_endpoint_does_not_exist(client) -> None:
    token = mint_token()
    response = await client.get(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {token}"},
        params={"name": "John"},
    )
    assert response.status_code == 404
    listed = [getattr(route, "path", "") for route in create_app(make_settings()).routes]
    assert not any("name" in path and "patient" in path for path in listed)
