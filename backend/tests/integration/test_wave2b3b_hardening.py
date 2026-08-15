import asyncio
import os
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import mint_token
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave2b3b_allergy import _amend_body, _penicillin

pytestmark = [pytest.mark.integration]

APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


@requires_db
async def test_concurrent_amend_and_concurrent_entered_in_error(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id, severity="MODERATE"),
    )
    allergy_id = created.json()["id"]

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/allergies/{allergy_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    first, second = await asyncio.gather(amend(), amend())
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ALLERGY_AMENDED'
                """
            ),
            {"id": allergy_id},
        )
        assert events.scalar_one() == 1

    other = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id, severity="MILD"),
    )
    other_id = other.json()["id"]

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/allergies/{other_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(void(), void())
    assert sorted([left.status_code, right.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ALLERGY_ENTERED_IN_ERROR'
                """
            ),
            {"id": other_id},
        )
        assert events.scalar_one() == 1


@requires_db
async def test_concurrent_amend_versus_entered_in_error(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id),
    )
    allergy_id = created.json()["id"]

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/allergies/{allergy_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/allergies/{allergy_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(amend(), void())
    codes = {left.status_code, right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status, version FROM allergies WHERE id = :id"),
            {"id": allergy_id},
        )
        status, version = row.one()
        assert status == "ENTERED_IN_ERROR"
        assert version in {1, 2}
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ALLERGY_ENTERED_IN_ERROR'
                """
            ),
            {"id": allergy_id},
        )
        assert eie.scalar_one() == 1
        amended = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ALLERGY_AMENDED'
                """
            ),
            {"id": allergy_id},
        )
        assert amended.scalar_one() == (1 if version == 2 else 0)


@requires_db
async def test_active_entered_in_error_freezes_row_and_encounters(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id),
    )
    allergy_id = created.json()["id"]
    voided = await db_client.post(
        f"/api/v1/clinical/allergies/{allergy_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    blocked = await db_client.post(
        f"/api/v1/clinical/allergies/{allergy_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(),
    )
    assert blocked.status_code == 409
    blocked_eie = await db_client.post(
        f"/api/v1/clinical/allergies/{allergy_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_eie.status_code == 409

    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE allergies SET clinical_status = 'INACTIVE' WHERE id = :id"),
                    {"id": allergy_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE allergies SET severity = 'MILD' WHERE id = :id"),
                    {"id": allergy_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE allergies SET category = 'FOOD' WHERE id = :id"),
                    {"id": allergy_id},
                )
        audit = await connection.execute(
            text("SELECT action, metadata::text FROM audit_events WHERE resource_id = :id"),
            {"id": allergy_id},
        )
        rows = list(audit)
        assert {row[0] for row in rows} == {"ALLERGY_CREATED", "ALLERGY_ENTERED_IN_ERROR"}
        assert all("Penicillin" not in (row[1] or "") for row in rows)
        assert all("Anaphylaxis" not in (row[1] or "") for row in rows)
        assert all("SEVERE" not in (row[1] or "") for row in rows)
        assert all("HIGH" not in (row[1] or "") for row in rows)

    cancelled = await _open_encounter(db_client, clinician, patient_id)
    cancel = await db_client.post(
        f"/api/v1/clinical/encounters/{cancelled.json()['id']}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "CANCELLED"},
    )
    assert cancel.status_code == 200
    blocked_cancelled = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id, cancelled.json()["id"]),
    )
    assert blocked_cancelled.status_code == 409
    still_cancelled = await db_client.get(
        f"/api/v1/clinical/encounters/{cancelled.json()['id']}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert still_cancelled.json()["status"] == "CANCELLED"


@requires_db
async def test_allergy_authz_purpose_and_app_dml_immutability(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    org_admin = await seed_actor(
        db_engine, role_code=RoleCode.ORG_ADMIN, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id),
    )
    allergy_id = created.json()["id"]

    unauthenticated = await db_client.get(f"/api/v1/clinical/allergies/{allergy_id}")
    assert unauthenticated.status_code == 401
    invalid_purpose = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=clinician.headers(purpose="NOT_A_PURPOSE"),
    )
    assert invalid_purpose.status_code == 422
    unprovisioned = mint_token(sub="nobody-allergy-hardening")
    denied_jwt = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers={
            "Authorization": f"Bearer {unprovisioned}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert denied_jwt.status_code == 403
    registrar_read = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=registrar.headers(purpose="TREATMENT"),
    )
    assert registrar_read.status_code == 403
    assert "Penicillin" not in registrar_read.text
    assert "Anaphylaxis" not in registrar_read.text
    admin_create = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id),
    )
    assert admin_create.status_code == 403
    admin_read = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=org_admin.headers(purpose="TREATMENT"),
    )
    assert admin_read.status_code == 200
    cross_org = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross_org.status_code == 404
    assert "sqlalchemy" not in cross_org.text.lower()
    assert "Penicillin" not in cross_org.text
    put = await db_client.put(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={},
    )
    assert put.status_code == 405

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE allergies SET patient_identity_id = :pid WHERE id = :id"),
                        {"id": allergy_id, "pid": uuid4()},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE allergies SET code_display = 'Bypass' WHERE id = :id"),
                        {"id": allergy_id},
                    )
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM allergies WHERE id = :id"),
                        {"id": allergy_id},
                    )
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE allergies"))
    finally:
        await engine.dispose()
