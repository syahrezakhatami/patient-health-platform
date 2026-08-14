import pytest
from app.core.correlation import CORRELATION_HEADER

pytestmark = pytest.mark.unit


async def test_liveness(client) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_correlation_id_generated(client) -> None:
    response = await client.get("/api/v1/health/live")
    assert CORRELATION_HEADER in response.headers
    assert response.headers[CORRELATION_HEADER]


async def test_correlation_id_propagated(client) -> None:
    response = await client.get(
        "/api/v1/health/live",
        headers={CORRELATION_HEADER: "req-123"},
    )
    assert response.headers[CORRELATION_HEADER] == "req-123"


async def test_invalid_correlation_id_replaced(client) -> None:
    response = await client.get(
        "/api/v1/health/live",
        headers={CORRELATION_HEADER: "has space"},
    )
    assert response.headers[CORRELATION_HEADER] != "has space"


async def test_unknown_route_error_shape(client) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert "correlation_id" in body["error"]
    assert "Traceback" not in response.text
    assert "sqlalchemy" not in response.text.lower()


async def test_security_headers(client) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
