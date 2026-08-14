from datetime import timedelta

import pytest
from tests.conftest import mint_token

pytestmark = pytest.mark.security


async def test_unauthenticated_context_rejected(client) -> None:
    response = await client.get("/api/v1/auth/context")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_malformed_token_rejected(client) -> None:
    response = await client.get(
        "/api/v1/auth/context",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert response.status_code == 401


async def test_expired_token_rejected(client) -> None:
    token = mint_token(exp_delta=timedelta(minutes=-5))
    response = await client.get(
        "/api/v1/auth/context",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"].lower()


async def test_invalid_issuer_rejected(client) -> None:
    token = mint_token(iss="https://evil.example")
    response = await client.get(
        "/api/v1/auth/context",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "issuer" in response.json()["error"]["message"].lower()


async def test_invalid_audience_rejected(client) -> None:
    token = mint_token(aud="other-api")
    response = await client.get(
        "/api/v1/auth/context",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "audience" in response.json()["error"]["message"].lower()


async def test_alg_none_rejected(client) -> None:
    token = (
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
        "eyJzdWIiOiJ1c2VyLTEiLCJpc3MiOiJodHRwOi8vbG9jYWxob3N0OjgwODAvcmVhbG1zL3BocC1kZXYiLCJhdWQiOiJwaHAtYXBpIiwiZXhwIjo5OTk5OTk5OTk5fQ."
    )
    response = await client.get(
        "/api/v1/auth/context",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


async def test_valid_token_returns_subject_and_deny_decision(client) -> None:
    token = mint_token()
    response = await client.get(
        "/api/v1/auth/context",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "user-1"
    assert body["authorization"]["allowed"] is False
    assert body["authorization"]["reason"] == "deny_by_default"


async def test_payload_too_large(client) -> None:
    response = await client.post(
        "/api/v1/auth/context",
        content=b"x" * 2048,
        headers={"Content-Length": "2048", "Authorization": "Bearer x"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_cors_allows_configured_origin(client) -> None:
    response = await client.options(
        "/api/v1/health/live",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_cors_rejects_unknown_origin(client) -> None:
    response = await client.get(
        "/api/v1/health/live",
        headers={"Origin": "https://evil.example"},
    )
    assert response.headers.get("access-control-allow-origin") != "https://evil.example"
