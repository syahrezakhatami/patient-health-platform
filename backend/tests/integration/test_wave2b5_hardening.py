import asyncio
import inspect
import os
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.clinical.application.services import ClinicalService
from app.modules.clinical.infrastructure.repositories import ClinicalRepository
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
from tests.integration.test_wave2b5_procedure import _amend_body, _procedure

pytestmark = [pytest.mark.integration]

APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


def test_procedure_lock_is_select_for_update_not_redis() -> None:
    lock_source = inspect.getsource(ClinicalRepository.get_procedure_for_update)
    amend_source = inspect.getsource(ClinicalService.amend_procedure)
    eie_source = inspect.getsource(ClinicalService.mark_procedure_entered_in_error)
    assert "with_for_update" in lock_source
    assert "redis" not in amend_source.lower()
    assert "redis" not in eie_source.lower()


@requires_db
async def test_concurrent_amend_and_concurrent_entered_in_error(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id, note="concurrent amend"),
    )
    procedure_id = created.json()["id"]

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/procedures/{procedure_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    first, second = await asyncio.gather(amend(), amend())
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        amended = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'PROCEDURE_AMENDED'
                """
            ),
            {"id": procedure_id},
        )
        assert amended.scalar_one() == 1

    other = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id, note="concurrent eie"),
    )
    other_id = other.json()["id"]

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/procedures/{other_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(void(), void())
    assert sorted([left.status_code, right.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'PROCEDURE_ENTERED_IN_ERROR'
                """
            ),
            {"id": other_id},
        )
        assert eie.scalar_one() == 1
        version = await connection.execute(
            text("SELECT version FROM procedures WHERE id = :id"),
            {"id": other_id},
        )
        assert version.scalar_one() == 1


@requires_db
async def test_concurrent_amend_versus_entered_in_error(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id, note="amend vs eie"),
    )
    procedure_id = created.json()["id"]

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/procedures/{procedure_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/procedures/{procedure_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(amend(), void())
    codes = {left.status_code, right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status, version FROM procedures WHERE id = :id"),
            {"id": procedure_id},
        )
        status, version = row.one()
        assert status == "ENTERED_IN_ERROR"
        assert version in {1, 2}
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'PROCEDURE_ENTERED_IN_ERROR'
                """
            ),
            {"id": procedure_id},
        )
        assert eie.scalar_one() == 1
        amended = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'PROCEDURE_AMENDED'
                """
            ),
            {"id": procedure_id},
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
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(
            patient_id,
            encounter_id,
            note="freeze me",
            occurrence_at="2026-03-01T03:00:00Z",
        ),
    )
    assert created.json()["patient_identity_id"] == patient_id
    assert created.json()["encounter_id"] == encounter_id
    assert created.json()["version"] == 1
    procedure_id = created.json()["id"]
    first_amend = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="first correction", occurrence_at="2026-03-02T04:00:00Z"),
    )
    assert first_amend.status_code == 200
    assert first_amend.json()["status"] == "AMENDED"
    assert first_amend.json()["version"] == 2
    second_amend = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="second correction", occurrence_at="2026-03-03T05:00:00Z"),
    )
    assert second_amend.status_code == 200
    assert second_amend.json()["status"] == "AMENDED"
    assert second_amend.json()["version"] == 3
    noop = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="second correction", occurrence_at="2026-03-03T05:00:00Z"),
    )
    assert noop.status_code == 409
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="invalid procedure status transition"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE procedures SET status = 'ACTIVE' WHERE id = :id"),
                    {"id": procedure_id},
                )
    voided = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    assert voided.json()["version"] == 3
    blocked = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="after eie"),
    )
    assert blocked.status_code == 409
    blocked_eie = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_eie.status_code == 409
    blocked_revoke = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/revoke",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_revoke.status_code == 404
    blocked_status = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "EXPIRED"},
    )
    assert blocked_status.status_code == 404

    async with db_engine.connect() as connection:
        frozen_updates = (
            ("UPDATE procedures SET patient_identity_id = :pid WHERE id = :id", {"pid": uuid4()}),
            ("UPDATE procedures SET encounter_id = NULL WHERE id = :id", {}),
            ("UPDATE procedures SET organization_id = :pid WHERE id = :id", {"pid": uuid4()}),
            ("UPDATE procedures SET facility_id = NULL WHERE id = :id", {}),
            ("UPDATE procedures SET category = 'REPORTED' WHERE id = :id", {}),
            ("UPDATE procedures SET code_system = 'changed' WHERE id = :id", {}),
            ("UPDATE procedures SET code = 'changed' WHERE id = :id", {}),
            ("UPDATE procedures SET code_display = 'Bypass' WHERE id = :id", {}),
            ("UPDATE procedures SET recorder_id = :pid WHERE id = :id", {"pid": uuid4()}),
            ("UPDATE procedures SET recorded_at = now() WHERE id = :id", {}),
            ("UPDATE procedures SET provenance_id = NULL WHERE id = :id", {}),
            ("UPDATE procedures SET occurrence_at = now() WHERE id = :id", {}),
            ("UPDATE procedures SET note_text = 'bypass' WHERE id = :id", {}),
            ("UPDATE procedures SET status = 'ACTIVE' WHERE id = :id", {}),
            ("UPDATE procedures SET version = version + 1 WHERE id = :id", {}),
        )
        for statement, extra in frozen_updates:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text(statement),
                        {"id": procedure_id, **extra},
                    )
        with pytest.raises(Exception, match="cannot be deleted"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM procedures WHERE id = :id"),
                    {"id": procedure_id},
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
            "given_name": "Prc",
            "family_name": "Enc",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B5H"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Prc", family="EncSurv", birth="1982-02-02"),
    )
    source_encounter = await _open_encounter(db_client, clinician, source.json()["id"])
    historical = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(source.json()["id"], source_encounter.json()["id"]),
    )
    assert historical.status_code in {200, 201}
    assert historical.json()["patient_identity_id"] == source.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.5 hardening encounter bind",
            "evidence": merge_evidence("wave2b5-enc"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/procedures/{historical.json()['id']}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    rebound = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(source.json()["id"], source_encounter.json()["id"]),
    )
    assert rebound.status_code == 409
    survivor_write = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(source.json()["id"]),
    )
    assert survivor_write.json()["patient_identity_id"] == survivor.json()["id"]
    retired = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    rejected = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(retired),
    )
    assert rejected.status_code == 409
    missing = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(str(uuid4())),
    )
    assert missing.status_code == 404


@requires_db
async def test_procedure_authz_denied_audit_and_app_dml(db_client, db_engine) -> None:
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
    auditor = await seed_actor(
        db_engine, role_code=RoleCode.AUDITOR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    other_registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=other.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="treatment"),
        json=_procedure(patient_id, note="secret note"),
    )
    assert created.status_code in {200, 201}
    procedure_id = created.json()["id"]
    assert created.json()["status"] == "ACTIVE"
    assert created.json()["version"] == 1
    assert created.json()["category"] == "PERFORMED"

    unauthenticated = await db_client.get(f"/api/v1/clinical/procedures/{procedure_id}")
    assert unauthenticated.status_code == 401
    missing_purpose = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
    )
    assert missing_purpose.status_code == 422
    invalid_purpose = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=clinician.headers(purpose="NOT_A_PURPOSE"),
    )
    assert invalid_purpose.status_code == 422
    unprovisioned = mint_token(sub="nobody-procedure-hardening")
    denied_jwt = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers={
            "Authorization": f"Bearer {unprovisioned}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert denied_jwt.status_code == 403
    registrar_read = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=registrar.headers(purpose="TREATMENT"),
    )
    assert registrar_read.status_code == 403
    assert "secret note" not in registrar_read.text
    assert "Appendectomy" not in registrar_read.text
    assert "80146002" not in registrar_read.text
    officer_read = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=officer.headers(purpose="TREATMENT"),
    )
    assert officer_read.status_code == 403
    assert "secret note" not in officer_read.text
    admin_create = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_procedure(patient_id),
    )
    assert admin_create.status_code == 403
    admin_read = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=org_admin.headers(purpose="TREATMENT"),
    )
    assert admin_read.status_code == 200
    auditor_read = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=auditor.headers(purpose="AUDIT"),
    )
    assert auditor_read.status_code == 200
    cross_org = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross_org.status_code == 404
    assert "sqlalchemy" not in cross_org.text.lower()
    assert "secret note" not in cross_org.text
    assert "Appendectomy" not in cross_org.text
    assert "80146002" not in cross_org.text
    foreign_patient = await _active_patient(db_client, other_registrar)
    cross_identity = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(foreign_patient),
    )
    assert cross_identity.status_code == 404
    put = await db_client.put(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={},
    )
    assert put.status_code == 405
    patch = await db_client.patch(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"note_text": "patched"},
    )
    assert patch.status_code == 405
    deleted = await db_client.delete(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
    v2 = await db_client.get(
        f"/api/v2/clinical/procedures/{procedure_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert v2.status_code == 404
    fhir = await db_client.get(
        f"/fhir/Procedure/{procedure_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fhir.status_code == 404
    fhir_root = await db_client.get(
        "/fhir/",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fhir_root.status_code == 404

    registrar_create = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_procedure(patient_id, note="denied payload"),
    )
    assert registrar_create.status_code == 403
    async with db_engine.connect() as connection:
        denied_rows = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE action = 'clinical.procedure.create' AND result = 'DENIED'
                """
            )
        )
        assert denied_rows.scalar_one() == 0
        created_audit = await connection.execute(
            text(
                """
                SELECT metadata::text FROM audit_events
                WHERE resource_id = :id AND action = 'PROCEDURE_CREATED'
                """
            ),
            {"id": procedure_id},
        )
        metadata = created_audit.scalar_one()
        assert "TREATMENT" in metadata
        assert "Appendectomy" not in metadata
        assert "secret note" not in metadata
        assert "80146002" not in metadata
        provenance = await connection.execute(
            text(
                """
                SELECT count(*) FROM procedures
                WHERE provenance_id IS NULL
                   OR provenance_id NOT IN (SELECT id FROM clinical_provenances)
                """
            )
        )
        assert provenance.scalar_one() == 0
        subject = await connection.execute(
            text(
                """
                SELECT subject_type FROM clinical_provenances
                WHERE id = (SELECT provenance_id FROM procedures WHERE id = :id)
                """
            ),
            {"id": procedure_id},
        )
        assert subject.scalar_one() == "PROCEDURE"

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE procedures SET patient_identity_id = :pid WHERE id = :id"),
                        {"id": procedure_id, "pid": uuid4()},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE procedures SET code_display = 'Bypass' WHERE id = :id"),
                        {"id": procedure_id},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE procedures SET code_system = 'changed' WHERE id = :id"),
                        {"id": procedure_id},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE procedures SET provenance_id = NULL WHERE id = :id"),
                        {"id": procedure_id},
                    )
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM procedures WHERE id = :id"),
                        {"id": procedure_id},
                    )
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE procedures"))
            with pytest.raises(Exception, match="procedure_category|check constraint"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            """
                            INSERT INTO procedures (
                                id, patient_identity_id, organization_id, category,
                                code_system, code, status, recorded_at, version,
                                provenance_id
                            )
                            SELECT gen_random_uuid(), patient_identity_id, organization_id,
                                   'PLANNED', code_system, code, 'ACTIVE', now(), 1,
                                   provenance_id
                            FROM procedures WHERE id = :id
                            """
                        ),
                        {"id": procedure_id},
                    )
            with pytest.raises(Exception, match="procedure_status|check constraint"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            """
                            INSERT INTO procedures (
                                id, patient_identity_id, organization_id, category,
                                code_system, code, status, recorded_at, version,
                                provenance_id
                            )
                            SELECT gen_random_uuid(), patient_identity_id, organization_id,
                                   category, code_system, code, 'EXPIRED', now(), 1,
                                   provenance_id
                            FROM procedures WHERE id = :id
                            """
                        ),
                        {"id": procedure_id},
                    )
            with pytest.raises(Exception, match="procedure_version_positive|check constraint"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            """
                            INSERT INTO procedures (
                                id, patient_identity_id, organization_id, category,
                                code_system, code, status, recorded_at, version,
                                provenance_id
                            )
                            SELECT gen_random_uuid(), patient_identity_id, organization_id,
                                   category, code_system, code, 'ACTIVE', now(), 0,
                                   provenance_id
                            FROM procedures WHERE id = :id
                            """
                        ),
                        {"id": procedure_id},
                    )
    finally:
        await engine.dispose()


@requires_db
async def test_platform_admin_reported_occurrence_anonymous_and_encounters(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    platform = await seed_actor(
        db_engine, role_code=RoleCode.PLATFORM_ADMIN, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    reported = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=platform.headers(purpose="TREATMENT"),
        json=_procedure(
            patient_id,
            note="platform reported",
            category="REPORTED",
            occurrence_at="2026-04-01T01:00:00Z",
        ),
    )
    assert reported.status_code == 403
    clinician_reported = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(
            patient_id,
            note="clinician reported",
            category="REPORTED",
            occurrence_at="2026-04-01T01:00:00Z",
        ),
    )
    assert clinician_reported.status_code in {200, 201}
    procedure_id = clinician_reported.json()["id"]
    amended = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/amend",
        headers=platform.headers(purpose="TREATMENT"),
        json=_amend_body(note="platform reported", occurrence_at="2026-04-02T02:00:00Z"),
    )
    assert amended.status_code == 403
    voided = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/entered-in-error",
        headers=platform.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 403

    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=registrar.headers(purpose="EMERGENCY"),
        json={},
    )
    anonymous_id = anonymous.json()["id"]
    standalone = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(anonymous_id),
    )
    assert standalone.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE encounters SET encounter_class = 'AMB' WHERE id = :id"),
            {"id": emer.json()["id"]},
        )
    blocked_amb = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(anonymous_id, emer.json()["id"]),
    )
    assert blocked_amb.status_code == 409
    restored = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    allowed = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(anonymous_id, restored.json()["id"]),
    )
    assert allowed.status_code in {200, 201}

    cancelled = await _open_encounter(db_client, clinician, patient_id)
    cancel = await db_client.post(
        f"/api/v1/clinical/encounters/{cancelled.json()['id']}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "CANCELLED"},
    )
    assert cancel.status_code == 200
    blocked_cancelled = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id, cancelled.json()["id"]),
    )
    assert blocked_cancelled.status_code == 409
    still_cancelled = await db_client.get(
        f"/api/v1/clinical/encounters/{cancelled.json()['id']}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert still_cancelled.json()["status"] == "CANCELLED"
    erroneous = await _open_encounter(db_client, clinician, patient_id)
    mark_error = await db_client.post(
        f"/api/v1/clinical/encounters/{erroneous.json()['id']}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "ENTERED_IN_ERROR"},
    )
    assert mark_error.status_code == 200
    blocked_eie_enc = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id, erroneous.json()["id"]),
    )
    assert blocked_eie_enc.status_code == 409
    other_patient = await _active_patient(db_client, registrar)
    mismatch = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(
            patient_id, (await _open_encounter(db_client, clinician, other_patient)).json()["id"]
        ),
    )
    assert mismatch.status_code == 409
