from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.mpi.domain.enums import IdentifierType
from tests.conftest import mint_token
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_wave1_mpi import unique_nik

pytestmark = [pytest.mark.integration, pytest.mark.security]


@requires_db
async def test_unprovisioned_user_cannot_create_identity(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    token = mint_token(sub="nobody-unprovisioned")
    response = await db_client.post(
        "/api/v1/mpi/identities",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": str(actor.organization_id),
            "X-Purpose": "REGISTRATION",
        },
        json={
            "given_name": "No",
            "family_name": "User",
            "birth_date": "1990-01-01",
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": IdentifierType.NIK,
                    "identifier_value": unique_nik(),
                }
            ],
        },
    )
    assert response.status_code == 403


@requires_db
async def test_unauthorized_merge_and_verify_are_denied(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json={
            "given_name": "A",
            "family_name": "B",
            "birth_date": "1991-01-01",
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": IdentifierType.NIK,
                    "identifier_value": unique_nik(),
                }
            ],
        },
    )
    other = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json={
            "given_name": "C",
            "family_name": "D",
            "birth_date": "1992-01-01",
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": IdentifierType.NIK,
                    "identifier_value": unique_nik(),
                }
            ],
        },
    )
    verify = await db_client.post(
        f"/api/v1/mpi/identifiers/{created.json()['identifiers'][0]['id']}/verify",
        headers=registrar.headers(purpose="IDENTITY_RESOLUTION"),
        json={"method": "document_inspection"},
    )
    assert verify.status_code == 403
    merge = await db_client.post(
        "/api/v1/mpi/merge",
        headers=registrar.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": created.json()["id"],
            "target_identity_id": other.json()["id"],
            "reason": "not allowed",
            "evidence": [
                {
                    "evidence_type": "STAFF_REVIEW",
                    "evidence_source": "registrar",
                    "evidence_reference": "denied-merge",
                    "reviewer_reason": "Unauthorized merge attempt",
                    "reviewed_at": "2026-08-13T17:00:00+00:00",
                }
            ],
        },
    )
    assert merge.status_code == 403
    unmerge = await db_client.post(
        "/api/v1/mpi/unmerge",
        headers=registrar.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "merge_operation_id": created.json()["id"],
            "reason": "not allowed",
            "evidence": [
                {
                    "evidence_type": "STAFF_REVIEW",
                    "evidence_source": "registrar",
                    "evidence_reference": "denied-unmerge",
                    "reviewer_reason": "Unauthorized unmerge attempt",
                    "reviewed_at": "2026-08-13T17:00:00+00:00",
                }
            ],
        },
    )
    assert unmerge.status_code == 403


@requires_db
async def test_cross_organization_read_is_not_automatic(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=hospital_a.headers(),
        json={
            "given_name": "Cross",
            "family_name": "Org",
            "birth_date": "1970-01-01",
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": IdentifierType.NIK,
                    "identifier_value": unique_nik(),
                }
            ],
        },
    )
    identity_id = created.json()["id"]
    read = await db_client.get(
        f"/api/v1/mpi/identities/{identity_id}",
        headers=hospital_b.headers(purpose="ADMINISTRATION"),
    )
    assert read.status_code == 404


@requires_db
async def test_identifier_is_masked_and_errors_do_not_leak(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    nik = unique_nik()
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(),
        json={
            "given_name": "Mask",
            "family_name": "Me",
            "birth_date": "1975-05-05",
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": IdentifierType.NIK,
                    "identifier_value": nik,
                }
            ],
        },
    )
    assert nik not in created.text
    assert created.json()["identifiers"][0]["masked_value"].endswith(nik[-4:])
    missing = await db_client.get(
        f"/api/v1/mpi/identities/{uuid4()}",
        headers=actor.headers(purpose="ADMINISTRATION"),
    )
    assert missing.status_code == 404
    assert "sqlalchemy" not in missing.text.lower()
    assert "Traceback" not in missing.text


@requires_db
async def test_malformed_identity_uuid_is_validation_error(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    response = await db_client.get(
        "/api/v1/mpi/identities/not-a-uuid",
        headers=actor.headers(purpose="ADMINISTRATION"),
    )
    assert response.status_code == 422
    assert "sqlalchemy" not in response.text.lower()
    assert "Traceback" not in response.text


@requires_db
async def test_idor_random_identity_is_not_found(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    response = await db_client.get(
        f"/api/v1/mpi/identities/{uuid4()}",
        headers=actor.headers(purpose="ADMINISTRATION"),
    )
    assert response.status_code == 404
