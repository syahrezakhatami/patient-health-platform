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
from tests.integration.test_wave2b3a_medication import _paracetamol
from tests.integration.test_wave2b3c_consent import _consent
from tests.integration.test_wave2b5_procedure import _procedure
from tests.integration.test_wave2b6_medical_device import _device
from tests.integration.test_wave2b7_adverse_event import _amend_body, _event

pytestmark = [pytest.mark.integration]

APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


def test_adverse_event_lock_is_select_for_update_not_redis() -> None:
    lock_source = inspect.getsource(ClinicalRepository.get_adverse_event_for_update)
    amend_source = inspect.getsource(ClinicalService.amend_adverse_event)
    eie_source = inspect.getsource(ClinicalService.mark_adverse_event_entered_in_error)
    related_source = inspect.getsource(ClinicalService._require_related_adverse_event_fact)
    assert "with_for_update" in lock_source
    assert "redis" not in amend_source.lower()
    assert "redis" not in eie_source.lower()
    assert "redis" not in related_source.lower()


def test_wave1_pdp_and_rate_limit_boundaries() -> None:
    pdp_source = inspect.getsource(Wave1PolicyPDP)
    assert "Role names are never inspected" in pdp_source
    assert "if role" not in pdp_source
    assert "Consent" not in pdp_source
    assert Settings.model_fields["rate_limit_per_minute"].default == 120


def test_trigger_allows_severity_until_entered_in_error() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260814_0016_wave2b7_adverse_events.py"
    )
    source = migration.read_text(encoding="utf-8")
    assert "NEW.severity IS DISTINCT FROM OLD.severity" not in source
    assert "NEW.category IS DISTINCT FROM OLD.category" in source
    assert "NEW.medication_id IS DISTINCT FROM OLD.medication_id" in source
    assert "entered-in-error adverse event is immutable" in source


@requires_db
async def test_concurrent_amend_and_concurrent_entered_in_error(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, note="concurrent amend"),
    )
    event_id = created.json()["id"]

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/adverse-events/{event_id}/amend",
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
                WHERE resource_id = :id AND action = 'ADVERSE_EVENT_AMENDED'
                """
            ),
            {"id": event_id},
        )
        assert amended.scalar_one() == 1

    other = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, note="concurrent eie"),
    )
    other_id = other.json()["id"]

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/adverse-events/{other_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(void(), void())
    assert sorted([left.status_code, right.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ADVERSE_EVENT_ENTERED_IN_ERROR'
                """
            ),
            {"id": other_id},
        )
        assert eie.scalar_one() == 1
        version = await connection.execute(
            text("SELECT version FROM adverse_events WHERE id = :id"),
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
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, note="amend vs eie"),
    )
    event_id = created.json()["id"]

    async def amend_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/adverse-events/{event_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    async def void_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/adverse-events/{event_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(amend_race(), void_race())
    codes = {left.status_code, right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status FROM adverse_events WHERE id = :id"),
            {"id": event_id},
        )
        assert row.scalar_one() == "ENTERED_IN_ERROR"
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ADVERSE_EVENT_ENTERED_IN_ERROR'
                """
            ),
            {"id": event_id},
        )
        amended = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ADVERSE_EVENT_AMENDED'
                """
            ),
            {"id": event_id},
        )
        assert eie.scalar_one() == 1
        assert amended.scalar_one() in {0, 1}


@requires_db
async def test_severity_is_amendable_until_entered_in_error(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, note="severity contract", severity="MILD"),
    )
    assert created.status_code in {200, 201}
    event_id = created.json()["id"]
    assert created.json()["severity"] == "MILD"
    extra_immutable = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json={
            "note_text": created.json()["note_text"],
            "occurrence_at": created.json()["occurrence_at"],
            "severity": "MILD",
            "category": "REPORTED",
            "patient_identity_id": str(uuid4()),
            "medication_id": str(uuid4()),
            "code": {"system": "changed", "code": "changed", "display": "Shock"},
        },
    )
    assert extra_immutable.status_code in {409, 422}
    still = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert still.json()["status"] == "ACTIVE"
    assert still.json()["version"] == 1
    assert still.json()["severity"] == "MILD"
    assert still.json()["category"] == "DOCUMENTED"
    assert still.json()["code"]["code"] == "39579001"
    first = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="first correction", severity="MODERATE"),
    )
    assert first.status_code == 200
    assert first.json()["status"] == "AMENDED"
    assert first.json()["version"] == 2
    assert first.json()["severity"] == "MODERATE"
    second = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="second correction", severity="SEVERE"),
    )
    assert second.status_code == 200
    assert second.json()["status"] == "AMENDED"
    assert second.json()["version"] == 3
    assert second.json()["severity"] == "SEVERE"
    noop = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="second correction", severity="SEVERE"),
    )
    assert noop.status_code == 409
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE adverse_events SET severity = 'MILD' WHERE id = :id"),
            {"id": event_id},
        )
    async with db_engine.connect() as connection:
        current = await connection.execute(
            text("SELECT severity, status, version FROM adverse_events WHERE id = :id"),
            {"id": event_id},
        )
        row = current.one()
        assert row[0] == "MILD"
        assert row[1] == "AMENDED"
        assert row[2] == 3
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="invalid adverse event status transition"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE adverse_events SET status = 'ACTIVE' WHERE id = :id"),
                    {"id": event_id},
                )
    restored = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="restore severe", severity="SEVERE"),
    )
    assert restored.status_code == 200
    assert restored.json()["version"] == 4
    voided = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    assert voided.json()["version"] == 4
    blocked = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="after eie", severity="MILD"),
    )
    assert blocked.status_code == 409
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE adverse_events SET severity = 'MILD' WHERE id = :id"),
                    {"id": event_id},
                )


@requires_db
async def test_related_fact_sql_invariant_and_no_target_mutation(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    medication = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(patient_id),
    )
    device = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(patient_id),
    )
    procedure = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id),
    )
    medication_id = medication.json()["id"]
    device_id = device.json()["id"]
    procedure_id = procedure.json()["id"]
    med_before = (medication.json()["status"], medication.json()["version"])
    device_before = (device.json()["status"], device.json()["version"])
    proc_before = (procedure.json()["status"], procedure.json()["version"])

    none = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id),
    )
    med_only = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, medication_id=medication_id),
    )
    device_only = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, medical_device_id=device_id),
    )
    proc_only = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, procedure_id=procedure_id),
    )
    assert none.status_code in {200, 201}
    assert med_only.status_code in {200, 201}
    assert device_only.status_code in {200, 201}
    assert proc_only.status_code in {200, 201}

    after_med = await db_client.get(
        f"/api/v1/clinical/medications/{medication_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    after_device = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    after_proc = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert (after_med.json()["status"], after_med.json()["version"]) == med_before
    assert (after_device.json()["status"], after_device.json()["version"]) == device_before
    assert (after_proc.json()["status"], after_proc.json()["version"]) == proc_before

    event_id = med_only.json()["id"]
    async with db_engine.connect() as connection:
        pairs = (
            (medication_id, device_id, None),
            (medication_id, None, procedure_id),
            (None, device_id, procedure_id),
        )
        for med, dev, proc in pairs:
            with pytest.raises(Exception, match="related_fact_at_most_one|check constraint"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            """
                            INSERT INTO adverse_events (
                                id, patient_identity_id, organization_id, category,
                                code_system, code, severity, medication_id,
                                medical_device_id, procedure_id, status, recorded_at, version
                            )
                            SELECT gen_random_uuid(), patient_identity_id, organization_id,
                                   category, code_system, code, severity, :med, :dev, :proc,
                                   'ACTIVE', now(), 1
                            FROM adverse_events WHERE id = :id
                            """
                        ),
                        {"id": event_id, "med": med, "dev": dev, "proc": proc},
                    )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE adverse_events SET medication_id = NULL WHERE id = :id"),
                    {"id": event_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE adverse_events SET medical_device_id = :dev WHERE id = :id"),
                    {"id": event_id, "dev": device_id},
                )
    async with db_engine.connect() as connection:
        fks = await connection.execute(
            text(
                """
                SELECT constraint_name, delete_rule
                FROM information_schema.referential_constraints
                WHERE constraint_name IN (
                    'fk_adverse_events_medication_id',
                    'fk_adverse_events_medical_device_id',
                    'fk_adverse_events_procedure_id'
                )
                """
            )
        )
        rules = {name: rule for name, rule in fks}
        assert rules["fk_adverse_events_medication_id"] == "RESTRICT"
        assert rules["fk_adverse_events_medical_device_id"] == "RESTRICT"
        assert rules["fk_adverse_events_procedure_id"] == "RESTRICT"
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="cannot be deleted|foreign key"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM medications WHERE id = :id"),
                    {"id": medication_id},
                )
    async with db_engine.connect() as connection:
        still = await connection.execute(
            text("SELECT medication_id, status FROM adverse_events WHERE id = :id"),
            {"id": event_id},
        )
        row = still.one()
        assert str(row[0]) == medication_id
        assert row[1] == "ACTIVE"


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
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, encounter_id, note="immutable row"),
    )
    event_id = created.json()["id"]
    async with db_engine.connect() as connection:
        created_updates = (
            (
                "UPDATE adverse_events SET patient_identity_id = :pid WHERE id = :id",
                {"pid": uuid4()},
            ),
            ("UPDATE adverse_events SET encounter_id = NULL WHERE id = :id", {}),
            ("UPDATE adverse_events SET organization_id = :pid WHERE id = :id", {"pid": uuid4()}),
            ("UPDATE adverse_events SET facility_id = :pid WHERE id = :id", {"pid": uuid4()}),
            ("UPDATE adverse_events SET category = 'REPORTED' WHERE id = :id", {}),
            ("UPDATE adverse_events SET code_system = 'changed' WHERE id = :id", {}),
            ("UPDATE adverse_events SET code = 'changed' WHERE id = :id", {}),
            ("UPDATE adverse_events SET code_display = 'Shock' WHERE id = :id", {}),
            ("UPDATE adverse_events SET recorder_id = :pid WHERE id = :id", {"pid": uuid4()}),
            ("UPDATE adverse_events SET recorded_at = now() WHERE id = :id", {}),
            ("UPDATE adverse_events SET provenance_id = NULL WHERE id = :id", {}),
            ("UPDATE adverse_events SET medication_id = :pid WHERE id = :id", {"pid": uuid4()}),
            ("UPDATE adverse_events SET medical_device_id = :pid WHERE id = :id", {"pid": uuid4()}),
            ("UPDATE adverse_events SET procedure_id = :pid WHERE id = :id", {"pid": uuid4()}),
        )
        for statement, extra in created_updates:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(text(statement), {"id": event_id, **extra})
    after_create = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert after_create.json()["status"] == encounter_before["status"]
    amended = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="first", severity="MODERATE"),
    )
    assert amended.status_code == 200
    assert amended.json()["version"] == 2
    after_amend = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert after_amend.json()["status"] == encounter_before["status"]
    voided = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/entered-in-error",
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
            ("UPDATE adverse_events SET occurrence_at = now() WHERE id = :id", {}),
            ("UPDATE adverse_events SET note_text = 'bypass' WHERE id = :id", {}),
            ("UPDATE adverse_events SET severity = 'MILD' WHERE id = :id", {}),
            ("UPDATE adverse_events SET status = 'ACTIVE' WHERE id = :id", {}),
            ("UPDATE adverse_events SET version = version + 1 WHERE id = :id", {}),
        )
        for statement, extra in frozen_updates:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(text(statement), {"id": event_id, **extra})
        with pytest.raises(Exception, match="cannot be deleted"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM adverse_events WHERE id = :id"),
                    {"id": event_id},
                )
    blocked_revoke = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/revoke",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_revoke.status_code == 404
    blocked_stop = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/stop",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_stop.status_code == 404
    async with db_engine.connect() as connection:
        privileges = await connection.execute(
            text(
                """
                SELECT privilege_type FROM information_schema.role_table_grants
                WHERE grantee = 'app_dml' AND table_name = 'adverse_events'
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
                text("SELECT id FROM adverse_events WHERE id = :id"),
                {"id": event_id},
            )
            assert str(selected.scalar_one()) == event_id
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE adverse_events SET category = 'REPORTED' WHERE id = :id"),
                        {"id": event_id},
                    )
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM adverse_events WHERE id = :id"),
                        {"id": event_id},
                    )
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE adverse_events"))
    finally:
        await engine.dispose()


@requires_db
async def test_adverse_event_authz_denied_audit_consent_and_platform(db_client, db_engine) -> None:
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
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="treatment"),
        json=_event(patient_id, note="secret note", category="REPORTED"),
    )
    assert created.status_code in {200, 201}
    event_id = created.json()["id"]
    assert created.json()["category"] == "REPORTED"
    consent = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id),
    )
    assert consent.status_code in {200, 201}
    registrar_create = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_event(patient_id, note="denied payload"),
    )
    assert registrar_create.status_code == 403
    assert "denied payload" not in registrar_create.text
    assert "Anaphylaxis" not in registrar_create.text
    officer_create = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=officer.headers(purpose="TREATMENT"),
        json=_event(patient_id),
    )
    assert officer_create.status_code == 403
    admin_create = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_event(patient_id),
    )
    assert admin_create.status_code == 403
    admin_amend = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_amend_body(),
    )
    assert admin_amend.status_code == 403
    auditor_amend = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=auditor.headers(purpose="AUDIT"),
        json=_amend_body(),
    )
    assert auditor_amend.status_code == 403
    cross = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "secret note" not in cross.text
    assert "Anaphylaxis" not in cross.text
    assert "sqlalchemy" not in cross.text.lower()
    assert "39579001" not in cross.text
    platform_created = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=platform.headers(purpose="TREATMENT"),
        json=_event(patient_id, note="platform", severity="MODERATE"),
    )
    assert platform_created.status_code == 403
    platform_amend = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=platform.headers(purpose="TREATMENT"),
        json=_amend_body(note="platform", severity="SEVERE"),
    )
    assert platform_amend.status_code == 403
    platform_eie = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/entered-in-error",
        headers=platform.headers(purpose="TREATMENT"),
    )
    assert platform_eie.status_code == 403
    async with db_engine.connect() as connection:
        denied_rows = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE action = 'clinical.adverse_event.create' AND result = 'DENIED'
                """
            )
        )
        assert denied_rows.scalar_one() == 0
        created_audit = await connection.execute(
            text(
                """
                SELECT metadata::text FROM audit_events
                WHERE resource_id = :id AND action = 'ADVERSE_EVENT_CREATED'
                """
            ),
            {"id": event_id},
        )
        metadata = created_audit.scalar_one()
        assert "TREATMENT" in metadata
        assert "REPORTED" in metadata
        assert "secret note" not in metadata
        assert "Anaphylaxis" not in metadata
        assert "39579001" not in metadata
        provenance = await connection.execute(
            text(
                """
                SELECT count(*) FROM adverse_events
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
                    'fhir_adverse_events','care_plans','vital_signs',
                    'diagnoses','patient_histories'
                  )
                """
            )
        )
        assert later.scalar_one() == 0
        forbidden_cols = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'adverse_events'
                  AND column_name IN (
                    'causality','outcome','life_threatening','seriousness',
                    'suspect_entity','notification_status'
                  )
                """
            )
        )
        assert forbidden_cols.scalar_one() == 0
        md_later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'fhir_devices','fhir_medical_devices','care_plans','vital_signs',
                    'diagnoses','patient_histories'
                  )
                """
            )
        )
        assert md_later.scalar_one() == 0


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
            "given_name": "Ae",
            "family_name": "Hard",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B7H"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Ae", family="HardSurv", birth="1982-02-02"),
    )
    source_encounter = await _open_encounter(db_client, clinician, source.json()["id"])
    historical = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(source.json()["id"], source_encounter.json()["id"]),
    )
    assert historical.json()["patient_identity_id"] == source.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.7 hardening encounter bind",
            "evidence": merge_evidence("wave2b7-hard"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/adverse-events/{historical.json()['id']}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    rebound = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(source.json()["id"], source_encounter.json()["id"]),
    )
    assert rebound.status_code == 409
    survivor_write = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(source.json()["id"]),
    )
    assert survivor_write.json()["patient_identity_id"] == survivor.json()["id"]
    retired = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    rejected = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(retired),
    )
    assert rejected.status_code == 409
    unauthenticated = await db_client.get(
        f"/api/v1/clinical/adverse-events/{historical.json()['id']}"
    )
    assert unauthenticated.status_code == 401
    unprovisioned = mint_token(sub="nobody-adverse-event-hardening")
    denied_jwt = await db_client.get(
        f"/api/v1/clinical/adverse-events/{historical.json()['id']}",
        headers={
            "Authorization": f"Bearer {unprovisioned}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert denied_jwt.status_code == 403
