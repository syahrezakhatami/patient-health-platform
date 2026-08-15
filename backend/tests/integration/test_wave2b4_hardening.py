import asyncio
import os
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import mint_token
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave2b4_immunization import _amend_body, _vaccine

pytestmark = [pytest.mark.integration]

APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


@requires_db
async def test_concurrent_amend_versus_entered_in_error(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(patient_id, note="amend vs eie"),
    )
    immunization_id = created.json()["id"]

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/immunizations/{immunization_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/immunizations/{immunization_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(amend(), void())
    codes = {left.status_code, right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status, version FROM immunizations WHERE id = :id"),
            {"id": immunization_id},
        )
        status, version = row.one()
        assert status == "ENTERED_IN_ERROR"
        assert version in {1, 2}
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'IMMUNIZATION_ENTERED_IN_ERROR'
                """
            ),
            {"id": immunization_id},
        )
        assert eie.scalar_one() == 1
        amended = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'IMMUNIZATION_AMENDED'
                """
            ),
            {"id": immunization_id},
        )
        assert amended.scalar_one() == (1 if version == 2 else 0)


@requires_db
async def test_entered_in_error_freezes_row_and_merged_encounter_binding(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    created = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(patient_id, encounter_id, note="freeze me"),
    )
    assert created.json()["patient_identity_id"] == patient_id
    assert created.json()["encounter_id"] == encounter_id
    assert created.json()["version"] == 1
    immunization_id = created.json()["id"]
    first_amend = await db_client.post(
        f"/api/v1/clinical/immunizations/{immunization_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="first correction", site="RIGHT_ARM"),
    )
    assert first_amend.status_code == 200
    assert first_amend.json()["status"] == "AMENDED"
    assert first_amend.json()["version"] == 2
    second_amend = await db_client.post(
        f"/api/v1/clinical/immunizations/{immunization_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="second correction", site="LEFT_THIGH"),
    )
    assert second_amend.status_code == 200
    assert second_amend.json()["status"] == "AMENDED"
    assert second_amend.json()["version"] == 3
    voided = await db_client.post(
        f"/api/v1/clinical/immunizations/{immunization_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    assert voided.json()["version"] == 3
    blocked = await db_client.post(
        f"/api/v1/clinical/immunizations/{immunization_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="after eie"),
    )
    assert blocked.status_code == 409
    blocked_eie = await db_client.post(
        f"/api/v1/clinical/immunizations/{immunization_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_eie.status_code == 409

    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE immunizations SET note_text = 'bypass' WHERE id = :id"),
                    {"id": immunization_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE immunizations SET route = 'SC' WHERE id = :id"),
                    {"id": immunization_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE immunizations SET site = 'OTHER' WHERE id = :id"),
                    {"id": immunization_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE immunizations SET occurrence_at = now() WHERE id = :id"),
                    {"id": immunization_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE immunizations SET category = 'REPORTED' WHERE id = :id"),
                    {"id": immunization_id},
                )
        still_encounter = await connection.execute(
            text("SELECT status FROM encounters WHERE id = :id"),
            {"id": encounter_id},
        )
        assert still_encounter.scalar_one() != "ENTERED_IN_ERROR"

    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Imm",
            "family_name": "Enc",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B4H"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Imm", family="EncSurv", birth="1982-02-02"),
    )
    source_encounter = await _open_encounter(db_client, clinician, source.json()["id"])
    historical = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(source.json()["id"], source_encounter.json()["id"]),
    )
    assert historical.status_code in {200, 201}
    assert historical.json()["patient_identity_id"] == source.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.4 hardening encounter bind",
            "evidence": merge_evidence("wave2b4-enc"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/immunizations/{historical.json()['id']}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    rebound = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(source.json()["id"], source_encounter.json()["id"]),
    )
    assert rebound.status_code == 409
    survivor_write = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(source.json()["id"]),
    )
    assert survivor_write.json()["patient_identity_id"] == survivor.json()["id"]


@requires_db
async def test_immunization_authz_denied_audit_and_app_dml(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    org_admin = await seed_actor(
        db_engine, role_code=RoleCode.ORG_ADMIN, organization_id=clinician.organization_id
    )
    platform = await seed_actor(
        db_engine, role_code=RoleCode.PLATFORM_ADMIN, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    other_registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=other.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="treatment"),
        json=_vaccine(patient_id, note="secret note"),
    )
    assert created.status_code in {200, 201}
    immunization_id = created.json()["id"]
    assert created.json()["status"] == "ACTIVE"
    assert created.json()["version"] == 1

    unauthenticated = await db_client.get(f"/api/v1/clinical/immunizations/{immunization_id}")
    assert unauthenticated.status_code == 401
    invalid_purpose = await db_client.get(
        f"/api/v1/clinical/immunizations/{immunization_id}",
        headers=clinician.headers(purpose="NOT_A_PURPOSE"),
    )
    assert invalid_purpose.status_code == 422
    unprovisioned = mint_token(sub="nobody-immunization-hardening")
    denied_jwt = await db_client.get(
        f"/api/v1/clinical/immunizations/{immunization_id}",
        headers={
            "Authorization": f"Bearer {unprovisioned}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert denied_jwt.status_code == 403
    registrar_read = await db_client.get(
        f"/api/v1/clinical/immunizations/{immunization_id}",
        headers=registrar.headers(purpose="TREATMENT"),
    )
    assert registrar_read.status_code == 403
    assert "secret note" not in registrar_read.text
    assert "COVID-19 vaccine" not in registrar_read.text
    assert "208" not in registrar_read.text
    officer_read = await db_client.get(
        f"/api/v1/clinical/immunizations/{immunization_id}",
        headers=officer.headers(purpose="TREATMENT"),
    )
    assert officer_read.status_code == 403
    assert "secret note" not in officer_read.text
    admin_create = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_vaccine(patient_id),
    )
    assert admin_create.status_code == 403
    admin_read = await db_client.get(
        f"/api/v1/clinical/immunizations/{immunization_id}",
        headers=org_admin.headers(purpose="TREATMENT"),
    )
    assert admin_read.status_code == 200
    platform_create = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=platform.headers(purpose="TREATMENT"),
        json=_vaccine(patient_id, note="platform write"),
    )
    assert platform_create.status_code in {200, 201}
    cross_org = await db_client.get(
        f"/api/v1/clinical/immunizations/{immunization_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross_org.status_code == 404
    assert "sqlalchemy" not in cross_org.text.lower()
    assert "secret note" not in cross_org.text
    assert "COVID-19 vaccine" not in cross_org.text
    assert "208" not in cross_org.text
    foreign_patient = await _active_patient(db_client, other_registrar)
    cross_identity = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(foreign_patient),
    )
    assert cross_identity.status_code == 404
    put = await db_client.put(
        f"/api/v1/clinical/immunizations/{immunization_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={},
    )
    assert put.status_code == 405
    patch = await db_client.patch(
        f"/api/v1/clinical/immunizations/{immunization_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"note_text": "patched"},
    )
    assert patch.status_code == 405
    deleted = await db_client.delete(
        f"/api/v1/clinical/immunizations/{immunization_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
    v2 = await db_client.get(
        f"/api/v2/clinical/immunizations/{immunization_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert v2.status_code == 404
    fhir = await db_client.get(
        f"/fhir/Immunization/{immunization_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fhir.status_code == 404

    registrar_create = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_vaccine(patient_id, note="denied payload"),
    )
    assert registrar_create.status_code == 403
    async with db_engine.connect() as connection:
        denied_rows = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE action = 'clinical.immunization.create' AND result = 'DENIED'
                """
            )
        )
        assert denied_rows.scalar_one() == 0
        created_audit = await connection.execute(
            text(
                """
                SELECT metadata::text FROM audit_events
                WHERE resource_id = :id AND action = 'IMMUNIZATION_CREATED'
                """
            ),
            {"id": immunization_id},
        )
        metadata = created_audit.scalar_one()
        assert "TREATMENT" in metadata
        assert "COVID-19 vaccine" not in metadata
        assert "secret note" not in metadata
        assert "208" not in metadata
        provenance = await connection.execute(
            text(
                """
                SELECT count(*) FROM immunizations
                WHERE provenance_id IS NULL
                   OR provenance_id NOT IN (SELECT id FROM clinical_provenances)
                """
            )
        )
        assert provenance.scalar_one() == 0

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE immunizations SET patient_identity_id = :pid WHERE id = :id"),
                        {"id": immunization_id, "pid": uuid4()},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE immunizations SET code_display = 'Bypass' WHERE id = :id"),
                        {"id": immunization_id},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE immunizations SET code_system = 'changed' WHERE id = :id"),
                        {"id": immunization_id},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE immunizations SET provenance_id = NULL WHERE id = :id"),
                        {"id": immunization_id},
                    )
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM immunizations WHERE id = :id"),
                        {"id": immunization_id},
                    )
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE immunizations"))
    finally:
        await engine.dispose()


@requires_db
async def test_anonymous_non_emer_and_active_eie_version(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=registrar.headers(purpose="EMERGENCY"),
        json={},
    )
    anonymous_id = anonymous.json()["id"]
    standalone = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(anonymous_id),
    )
    assert standalone.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE encounters SET encounter_class = 'AMB' WHERE id = :id"),
            {"id": emer.json()["id"]},
        )
    blocked_amb = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(anonymous_id, emer.json()["id"]),
    )
    assert blocked_amb.status_code == 409
    restored = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    allowed = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(anonymous_id, restored.json()["id"]),
    )
    assert allowed.status_code in {200, 201}

    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(patient_id, note="active eie"),
    )
    immunization_id = created.json()["id"]
    voided = await db_client.post(
        f"/api/v1/clinical/immunizations/{immunization_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    assert voided.json()["version"] == 1
