import asyncio
import inspect
import os
from pathlib import Path
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
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
from tests.integration.test_wave2b1_condition import _pneumonia
from tests.integration.test_wave2b3c_consent import _consent
from tests.integration.test_wave2b8_family_history import _amend_body, _history

pytestmark = [pytest.mark.integration]

APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


def test_family_history_lock_is_select_for_update_not_redis() -> None:
    lock_source = inspect.getsource(ClinicalRepository.get_family_history_for_update)
    amend_source = inspect.getsource(ClinicalService.amend_family_history)
    eie_source = inspect.getsource(ClinicalService.mark_family_history_entered_in_error)
    assert "with_for_update" in lock_source
    assert "redis" not in amend_source.lower()
    assert "redis" not in eie_source.lower()


def test_wave1_pdp_and_rate_limit_boundaries() -> None:
    pdp_source = inspect.getsource(Wave1PolicyPDP)
    assert "Role names are never inspected" in pdp_source
    assert "if role" not in pdp_source
    assert "Consent" not in pdp_source
    assert Settings.model_fields["rate_limit_per_minute"].default == 120


def test_trigger_allows_occurrence_and_note_until_entered_in_error() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260814_0017_wave2b8_family_histories.py"
    )
    source = migration.read_text(encoding="utf-8")
    assert "NEW.occurrence_at IS DISTINCT FROM OLD.occurrence_at" not in source
    assert "NEW.note_text IS DISTINCT FROM OLD.note_text" not in source
    assert "NEW.relationship IS DISTINCT FROM OLD.relationship" in source
    assert "NEW.category IS DISTINCT FROM OLD.category" in source
    assert "NEW.code_system IS DISTINCT FROM OLD.code_system" in source
    assert "NEW.code IS DISTINCT FROM OLD.code" in source
    assert "NEW.code_display IS DISTINCT FROM OLD.code_display" in source
    assert "entered-in-error family history is immutable" in source


@requires_db
async def test_concurrent_amend_and_concurrent_entered_in_error(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id, note="concurrent amend"),
    )
    history_id = created.json()["id"]

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/family-histories/{history_id}/amend",
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
                WHERE resource_id = :id AND action = 'FAMILY_HISTORY_AMENDED'
                """
            ),
            {"id": history_id},
        )
        assert amended.scalar_one() == 1
        version = await connection.execute(
            text("SELECT version FROM family_histories WHERE id = :id"),
            {"id": history_id},
        )
        assert version.scalar_one() == 2

    other = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id, note="concurrent eie"),
    )
    other_id = other.json()["id"]

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/family-histories/{other_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(void(), void())
    assert sorted([left.status_code, right.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'FAMILY_HISTORY_ENTERED_IN_ERROR'
                """
            ),
            {"id": other_id},
        )
        assert eie.scalar_one() == 1
        version = await connection.execute(
            text("SELECT version FROM family_histories WHERE id = :id"),
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
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id, note="amend vs eie"),
    )
    history_id = created.json()["id"]

    async def amend_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/family-histories/{history_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    async def void_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/family-histories/{history_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(amend_race(), void_race())
    codes = {left.status_code, right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status FROM family_histories WHERE id = :id"),
            {"id": history_id},
        )
        assert row.scalar_one() == "ENTERED_IN_ERROR"
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'FAMILY_HISTORY_ENTERED_IN_ERROR'
                """
            ),
            {"id": history_id},
        )
        amended = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'FAMILY_HISTORY_AMENDED'
                """
            ),
            {"id": history_id},
        )
        assert eie.scalar_one() == 1
        assert amended.scalar_one() in {0, 1}


@requires_db
async def test_occurrence_and_note_are_amendable_until_entered_in_error(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(
            patient_id,
            note="occurrence contract",
            occurrence_at="2018-03-15T00:00:00Z",
            relationship="PARENT",
            category="DOCUMENTED",
        ),
    )
    assert created.status_code in {200, 201}
    history_id = created.json()["id"]
    assert created.json()["relationship"] == "PARENT"
    extra_immutable = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json={
            "note_text": created.json()["note_text"],
            "occurrence_at": created.json()["occurrence_at"],
            "relationship": "SIBLING",
            "category": "REPORTED",
            "patient_identity_id": str(uuid4()),
            "code": {"system": "changed", "code": "changed", "display": "Shock"},
        },
    )
    assert extra_immutable.status_code in {409, 422}
    still = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert still.json()["status"] == "ACTIVE"
    assert still.json()["version"] == 1
    assert still.json()["relationship"] == "PARENT"
    assert still.json()["category"] == "DOCUMENTED"
    assert still.json()["code"]["code"] == "254837009"
    first = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="first correction", occurrence_at="2019-01-01T00:00:00Z"),
    )
    assert first.status_code == 200
    assert first.json()["status"] == "AMENDED"
    assert first.json()["version"] == 2
    assert first.json()["note_text"] == "first correction"
    assert str(first.json()["occurrence_at"]).startswith("2019-01-01")
    assert first.json()["relationship"] == "PARENT"
    second = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="second correction", occurrence_at="2020-01-01T00:00:00Z"),
    )
    assert second.status_code == 200
    assert second.json()["status"] == "AMENDED"
    assert second.json()["version"] == 3
    assert second.json()["note_text"] == "second correction"
    noop = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="second correction", occurrence_at=second.json()["occurrence_at"]),
    )
    assert noop.status_code == 409
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE family_histories SET note_text = 'sql note', "
                "occurrence_at = TIMESTAMPTZ '2010-01-01 00:00:00+00' WHERE id = :id"
            ),
            {"id": history_id},
        )
    async with db_engine.connect() as connection:
        current = await connection.execute(
            text(
                "SELECT note_text, occurrence_at, status, version, relationship "
                "FROM family_histories WHERE id = :id"
            ),
            {"id": history_id},
        )
        row = current.one()
        assert row[0] == "sql note"
        assert str(row[1]).startswith("2010-01-01")
        assert row[2] == "AMENDED"
        assert row[3] == 3
        assert row[4] == "PARENT"
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="invalid family history status transition"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE family_histories SET status = 'ACTIVE' WHERE id = :id"),
                    {"id": history_id},
                )
    restored = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="restore note", occurrence_at="2021-01-01T00:00:00Z"),
    )
    assert restored.status_code == 200
    assert restored.json()["version"] == 4
    voided = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    assert voided.json()["version"] == 4
    blocked = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="after eie", occurrence_at="2022-01-01T00:00:00Z"),
    )
    assert blocked.status_code == 409
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE family_histories SET note_text = 'bypass' WHERE id = :id"),
                    {"id": history_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE family_histories SET occurrence_at = now() WHERE id = :id"),
                    {"id": history_id},
                )


@requires_db
async def test_immutable_columns_sql_api_and_app_dml(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter = await _open_encounter(db_client, clinician, patient_id)
    encounter_id = encounter.json()["id"]
    encounter_before = encounter.json()
    created = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id, encounter_id, note="immutable row"),
    )
    history_id = created.json()["id"]
    async with db_engine.connect() as connection:
        created_updates = (
            (
                "UPDATE family_histories SET patient_identity_id = :pid WHERE id = :id",
                {"pid": uuid4()},
            ),
            ("UPDATE family_histories SET encounter_id = NULL WHERE id = :id", {}),
            (
                "UPDATE family_histories SET organization_id = :pid WHERE id = :id",
                {"pid": uuid4()},
            ),
            ("UPDATE family_histories SET facility_id = :pid WHERE id = :id", {"pid": uuid4()}),
            ("UPDATE family_histories SET relationship = 'SIBLING' WHERE id = :id", {}),
            ("UPDATE family_histories SET category = 'REPORTED' WHERE id = :id", {}),
            ("UPDATE family_histories SET code_system = 'changed' WHERE id = :id", {}),
            ("UPDATE family_histories SET code = 'changed' WHERE id = :id", {}),
            ("UPDATE family_histories SET code_display = 'Shock' WHERE id = :id", {}),
            ("UPDATE family_histories SET recorder_id = :pid WHERE id = :id", {"pid": uuid4()}),
            ("UPDATE family_histories SET recorded_at = now() WHERE id = :id", {}),
            ("UPDATE family_histories SET provenance_id = NULL WHERE id = :id", {}),
        )
        for statement, extra in created_updates:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(text(statement), {"id": history_id, **extra})
    after_create = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert after_create.json()["status"] == encounter_before["status"]
    amended = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="first"),
    )
    assert amended.status_code == 200
    assert amended.json()["version"] == 2
    after_amend = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert after_amend.json()["status"] == encounter_before["status"]
    voided = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    after_eie = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert after_eie.json()["status"] == encounter_before["status"]
    async with db_engine.connect() as connection:
        frozen_updates = (
            ("UPDATE family_histories SET occurrence_at = now() WHERE id = :id", {}),
            ("UPDATE family_histories SET note_text = 'bypass' WHERE id = :id", {}),
            ("UPDATE family_histories SET status = 'ACTIVE' WHERE id = :id", {}),
            ("UPDATE family_histories SET version = version + 1 WHERE id = :id", {}),
        )
        for statement, extra in frozen_updates:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(text(statement), {"id": history_id, **extra})
        with pytest.raises(Exception, match="cannot be deleted|permission denied"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM family_histories WHERE id = :id"),
                    {"id": history_id},
                )
    blocked_revoke = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/revoke",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_revoke.status_code == 404
    blocked_stop = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/stop",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_stop.status_code == 404
    put = await db_client.put(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={},
    )
    assert put.status_code == 405
    patch = await db_client.patch(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"note_text": "patched"},
    )
    assert patch.status_code == 405
    deleted = await db_client.delete(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
    async with db_engine.connect() as connection:
        privileges = await connection.execute(
            text(
                """
                SELECT privilege_type FROM information_schema.role_table_grants
                WHERE grantee = 'app_dml' AND table_name = 'family_histories'
                """
            )
        )
        granted = {row[0] for row in privileges}
        assert {"SELECT", "INSERT", "UPDATE"}.issubset(granted)
        assert "DELETE" not in granted
        assert "TRUNCATE" not in granted
    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            selected = await connection.execute(
                text("SELECT id FROM family_histories WHERE id = :id"),
                {"id": history_id},
            )
            assert str(selected.scalar_one()) == history_id
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE family_histories SET relationship = 'COUSIN' WHERE id = :id"),
                        {"id": history_id},
                    )
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE family_histories SET category = 'REPORTED' WHERE id = :id"),
                        {"id": history_id},
                    )
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM family_histories WHERE id = :id"),
                        {"id": history_id},
                    )
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE family_histories"))
    finally:
        await engine.dispose()


@requires_db
async def test_family_history_authz_denied_audit_consent_and_platform(db_client, db_engine) -> None:
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
    platform = await seed_actor(
        db_engine, role_code=RoleCode.PLATFORM_ADMIN, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="treatment"),
        json=_history(patient_id, note="secret note", category="REPORTED", relationship="SIBLING"),
    )
    assert created.status_code in {200, 201}
    history_id = created.json()["id"]
    assert created.json()["category"] == "REPORTED"
    assert created.json()["relationship"] == "SIBLING"
    condition = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    assert condition.status_code in {200, 201}
    condition_id = condition.json()["id"]
    condition_clinical = condition.json()["clinical_status"]
    consent = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id),
    )
    assert consent.status_code in {200, 201}
    registrar_create = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_history(patient_id, note="denied payload"),
    )
    assert registrar_create.status_code == 403
    assert "denied payload" not in registrar_create.text
    assert "Breast cancer" not in registrar_create.text
    officer_create = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=officer.headers(purpose="TREATMENT"),
        json=_history(patient_id),
    )
    assert officer_create.status_code == 403
    admin_create = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_history(patient_id),
    )
    assert admin_create.status_code == 403
    admin_amend = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_amend_body(),
    )
    assert admin_amend.status_code == 403
    auditor_amend = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=auditor.headers(purpose="AUDIT"),
        json=_amend_body(),
    )
    assert auditor_amend.status_code == 403
    admin_read = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=org_admin.headers(purpose="TREATMENT"),
    )
    assert admin_read.status_code == 200
    auditor_read = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=auditor.headers(purpose="AUDIT"),
    )
    assert auditor_read.status_code == 200
    cross = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "secret note" not in cross.text
    assert "Breast cancer" not in cross.text
    assert "sqlalchemy" not in cross.text.lower()
    assert "254837009" not in cross.text
    platform_created = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=platform.headers(purpose="TREATMENT"),
        json=_history(patient_id, note="platform", relationship="COUSIN"),
    )
    assert platform_created.status_code == 403
    platform_amend = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=platform.headers(purpose="TREATMENT"),
        json=_amend_body(note="platform corrected"),
    )
    assert platform_amend.status_code == 403
    platform_eie = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/entered-in-error",
        headers=platform.headers(purpose="TREATMENT"),
    )
    assert platform_eie.status_code == 403
    after_condition = await db_client.get(
        f"/api/v1/clinical/conditions/{condition_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert after_condition.json()["clinical_status"] == condition_clinical
    assert history_id != condition_id
    v2 = await db_client.get(
        f"/api/v2/clinical/family-histories/{history_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert v2.status_code == 404
    fhir = await db_client.get(
        f"/fhir/FamilyMemberHistory/{history_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fhir.status_code == 404
    async with db_engine.connect() as connection:
        denied_rows = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE action = 'clinical.family_history.create' AND result = 'DENIED'
                """
            )
        )
        assert denied_rows.scalar_one() == 0
        created_audit = await connection.execute(
            text(
                """
                SELECT metadata::text FROM audit_events
                WHERE resource_id = :id AND action = 'FAMILY_HISTORY_CREATED'
                """
            ),
            {"id": history_id},
        )
        metadata = created_audit.scalar_one()
        assert "TREATMENT" in metadata
        assert "REPORTED" in metadata
        assert "SIBLING" in metadata
        assert "secret note" not in metadata
        assert "Breast cancer" not in metadata
        assert "254837009" not in metadata
        provenance = await connection.execute(
            text(
                """
                SELECT count(*) FROM family_histories
                WHERE provenance_id IS NULL
                   OR provenance_id NOT IN (SELECT id FROM clinical_provenances)
                """
            )
        )
        assert provenance.scalar_one() == 0
        later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'fhir_family_member_histories','care_plans','vital_signs',
                    'diagnoses','patient_histories','family_conditions'
                  )
                """
            )
        )
        assert later.scalar_one() == 0
        json_cols = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'family_histories'
                  AND data_type IN ('json', 'jsonb')
                """
            )
        )
        assert json_cols.scalar_one() == 0
        no_condition_fk = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_name = 'family_histories' AND column_name = 'condition_id'
                """
            )
        )
        assert no_condition_fk.scalar_one() == 0
        ae_later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'fhir_adverse_events','care_plans','vital_signs',
                    'diagnoses','patient_histories'
                  )
                """
            )
        )
        assert ae_later.scalar_one() == 0


@requires_db
async def test_merged_retired_and_anonymous_hardening(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Fh",
            "family_name": "Hard",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B8H"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Fh", family="HardSurv", birth="1982-02-02"),
    )
    source_encounter = await _open_encounter(db_client, clinician, source.json()["id"])
    historical = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(source.json()["id"], source_encounter.json()["id"]),
    )
    assert historical.json()["patient_identity_id"] == source.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.8 hardening encounter bind",
            "evidence": merge_evidence("wave2b8-hard"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/family-histories/{historical.json()['id']}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    rebound = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(source.json()["id"], source_encounter.json()["id"]),
    )
    assert rebound.status_code == 409
    survivor_write = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(source.json()["id"]),
    )
    assert survivor_write.json()["patient_identity_id"] == survivor.json()["id"]
    retired = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    rejected = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(retired),
    )
    assert rejected.status_code == 409
    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=registrar.headers(purpose="EMERGENCY"),
        json={},
    )
    anonymous_id = anonymous.json()["id"]
    standalone = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(anonymous_id),
    )
    assert standalone.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    allowed_emer = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(anonymous_id, emer.json()["id"]),
    )
    assert allowed_emer.status_code in {200, 201}
    unauthenticated = await db_client.get(
        f"/api/v1/clinical/family-histories/{historical.json()['id']}"
    )
    assert unauthenticated.status_code == 401
    unprovisioned = mint_token(sub="nobody-family-history-hardening")
    denied_jwt = await db_client.get(
        f"/api/v1/clinical/family-histories/{historical.json()['id']}",
        headers={
            "Authorization": f"Bearer {unprovisioned}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert denied_jwt.status_code == 403
