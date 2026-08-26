import asyncio
import inspect
import os
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.clinical.application.services import ClinicalService
from app.modules.clinical.infrastructure.repositories import ClinicalRepository
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.infrastructure.models import OrganizationMembershipModel, RoleModel, UserModel
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel
from app.shared.types.ids import new_id
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import mint_token
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave2b3a_medication import _paracetamol
from tests.integration.test_wave2b5_procedure import _procedure
from tests.integration.test_wave2b6_medical_device import _device
from tests.integration.test_wave15_hardening import _headers

pytestmark = [pytest.mark.integration]

SNOMED = "http://snomed.info/sct"
APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


def _event(
    patient_id: str,
    encounter_id: str | None = None,
    *,
    note: str | None = "Hives after first dose",
    category: str = "DOCUMENTED",
    severity: str = "MILD",
    occurrence_at: str | None = None,
    medication_id: str | None = None,
    medical_device_id: str | None = None,
    procedure_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "patient_identity_id": patient_id,
        "category": category,
        "code": {"system": SNOMED, "code": "39579001", "display": "Anaphylaxis"},
        "severity": severity,
    }
    if note is not None:
        payload["note_text"] = note
    if occurrence_at is not None:
        payload["occurrence_at"] = occurrence_at
    if encounter_id is not None:
        payload["encounter_id"] = encounter_id
    if medication_id is not None:
        payload["medication_id"] = medication_id
    if medical_device_id is not None:
        payload["medical_device_id"] = medical_device_id
    if procedure_id is not None:
        payload["procedure_id"] = procedure_id
    return payload


def _amend_body(
    *,
    note: str | None = "Corrected note",
    severity: str | None = None,
    occurrence_at: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"note_text": note}
    if severity is not None:
        payload["severity"] = severity
    if occurrence_at is not None:
        payload["occurrence_at"] = occurrence_at
    return payload


def test_adverse_event_lock_is_select_for_update_not_redis() -> None:
    lock_source = inspect.getsource(ClinicalRepository.get_adverse_event_for_update)
    amend_source = inspect.getsource(ClinicalService.amend_adverse_event)
    eie_source = inspect.getsource(ClinicalService.mark_adverse_event_entered_in_error)
    assert "with_for_update" in lock_source
    assert "redis" not in amend_source.lower()
    assert "redis" not in eie_source.lower()


@requires_db
async def test_adverse_event_lifecycle_identity_and_authorization(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    auditor = await seed_actor(
        db_engine, role_code=RoleCode.AUDITOR, organization_id=clinician.organization_id
    )
    org_admin = await seed_actor(
        db_engine, role_code=RoleCode.ORG_ADMIN, organization_id=clinician.organization_id
    )
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]

    invalid = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_event(patient_id), "category": "NOT_A_CATEGORY"},
    )
    assert invalid.status_code == 422
    invalid_code = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_event(patient_id), "code": {"system": "", "code": "39579001"}},
    )
    assert invalid_code.status_code == 422
    invalid_severity = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_event(patient_id), "severity": "LIFE_THREATENING"},
    )
    assert invalid_severity.status_code == 422

    created = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, encounter_id),
    )
    assert created.status_code in {200, 201}
    body = created.json()
    assert body["status"] == "ACTIVE"
    assert body["version"] == 1
    assert body["category"] == "DOCUMENTED"
    assert body["severity"] == "MILD"
    assert body["medication_id"] is None
    assert body["medical_device_id"] is None
    assert body["procedure_id"] is None
    event_id = body["id"]

    denied = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_event(patient_id),
    )
    assert denied.status_code == 403
    assert "Anaphylaxis" not in denied.text
    assert "Hives after first dose" not in denied.text
    officer_denied = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=officer.headers(purpose="TREATMENT"),
        json=_event(patient_id),
    )
    assert officer_denied.status_code == 403
    registrar_read = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=registrar.headers(purpose="TREATMENT"),
    )
    assert registrar_read.status_code == 403
    officer_read = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=officer.headers(purpose="TREATMENT"),
    )
    assert officer_read.status_code == 403

    listed = await db_client.get(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert listed.status_code == 200
    assert event_id in {item["id"] for item in listed.json()}

    auditor_read = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=auditor.headers(purpose="AUDIT"),
    )
    assert auditor_read.status_code == 200
    admin_create = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_event(patient_id),
    )
    assert admin_create.status_code == 403
    admin_read = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=org_admin.headers(purpose="TREATMENT"),
    )
    assert admin_read.status_code == 200
    platform_created = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=platform.headers(purpose="TREATMENT"),
        json=_event(patient_id),
    )
    assert platform_created.status_code == 403
    platform_read = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=platform.headers(purpose="TREATMENT"),
    )
    assert platform_read.status_code == 403

    amended = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(severity="SEVERE"),
    )
    assert amended.status_code == 200
    assert amended.json()["status"] == "AMENDED"
    assert amended.json()["note_text"] == "Corrected note"
    assert amended.json()["severity"] == "SEVERE"
    assert amended.json()["version"] == 2
    noop = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(severity="SEVERE"),
    )
    assert noop.status_code == 409

    voided = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    assert voided.json()["version"] == 2
    blocked = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="after eie"),
    )
    assert blocked.status_code == 409
    blocked_eie = await db_client.post(
        f"/api/v1/clinical/adverse-events/{event_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_eie.status_code == 409

    cross = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "sqlalchemy" not in cross.text.lower()
    assert "39579001" not in cross.text
    assert "Anaphylaxis" not in cross.text
    unknown = await db_client.get(
        f"/api/v1/clinical/adverse-events/{uuid4()}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unknown.status_code == 404
    deleted = await db_client.delete(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
    put = await db_client.put(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={},
    )
    assert put.status_code == 405
    patch = await db_client.patch(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"note_text": "patched"},
    )
    assert patch.status_code == 405
    v2 = await db_client.get(
        f"/api/v2/clinical/adverse-events/{event_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert v2.status_code == 404
    fhir = await db_client.get(
        f"/fhir/AdverseEvent/{event_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fhir.status_code == 404
    missing_purpose = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
    )
    assert missing_purpose.status_code == 422
    invalid_purpose = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=clinician.headers(purpose="NOT_A_PURPOSE"),
    )
    assert invalid_purpose.status_code == 422
    unauthenticated = await db_client.get(f"/api/v1/clinical/adverse-events/{event_id}")
    assert unauthenticated.status_code == 401
    unauthenticated_post = await db_client.post(
        "/api/v1/clinical/adverse-events",
        json=_event(patient_id),
    )
    assert unauthenticated_post.status_code == 401
    unprovisioned = mint_token(sub="nobody-adverse-event")
    denied_jwt = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers={
            "Authorization": f"Bearer {unprovisioned}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert denied_jwt.status_code == 403

    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE adverse_events SET patient_identity_id = :pid WHERE id = :id"),
                    {"id": event_id, "pid": uuid4()},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE adverse_events SET code = 'changed' WHERE id = :id"),
                    {"id": event_id},
                )
        with pytest.raises(Exception, match="cannot be deleted"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM adverse_events WHERE id = :id"),
                    {"id": event_id},
                )
        provenance = await connection.execute(
            text(
                """
                SELECT subject_type FROM clinical_provenances
                WHERE id = (SELECT provenance_id FROM adverse_events WHERE id = :id)
                """
            ),
            {"id": event_id},
        )
        assert provenance.scalar_one() == "ADVERSE_EVENT"
        fk = await connection.execute(
            text(
                """
                SELECT delete_rule FROM information_schema.referential_constraints
                WHERE constraint_name = 'fk_adverse_events_provenance_id'
                """
            )
        )
        assert fk.scalar_one() == "RESTRICT"
        audit = await connection.execute(
            text("SELECT action, metadata::text FROM audit_events WHERE resource_id = :id"),
            {"id": event_id},
        )
        rows = list(audit)
        actions = {row[0] for row in rows}
        assert "ADVERSE_EVENT_CREATED" in actions
        assert "ADVERSE_EVENT_AMENDED" in actions
        assert "ADVERSE_EVENT_ENTERED_IN_ERROR" in actions
        assert all("Anaphylaxis" not in (row[1] or "") for row in rows)
        assert all("Hives after first dose" not in (row[1] or "") for row in rows)
        assert all("39579001" not in (row[1] or "") for row in rows)
        later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'fhir_adverse_events','care_plans','vital_signs','patient_histories'
                  )
                """
            )
        )
        assert later.scalar_one() == 0
        present = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'adverse_events','medical_devices','procedures','immunizations'
                  )
                """
            )
        )
        assert present.scalar_one() == 4


@requires_db
async def test_anonymous_merged_and_encounter_adverse_event_binding(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    other_registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=other.organization_id
    )
    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=registrar.headers(purpose="EMERGENCY"),
        json={},
    )
    anonymous_id = anonymous.json()["id"]
    blocked = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(anonymous_id),
    )
    assert blocked.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE encounters SET encounter_class = 'AMB' WHERE id = :id"),
            {"id": emer.json()["id"]},
        )
    blocked_amb = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(anonymous_id, emer.json()["id"]),
    )
    assert blocked_amb.status_code == 409
    restored = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    allowed = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(anonymous_id, restored.json()["id"]),
    )
    assert allowed.status_code in {200, 201}

    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    foreign_patient = await _active_patient(db_client, other_registrar)
    mismatch = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(
            patient_id, (await _open_encounter(db_client, clinician, other_patient)).json()["id"]
        ),
    )
    assert mismatch.status_code == 409
    foreign = await _open_encounter(db_client, other, foreign_patient)
    cross_org = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, foreign.json()["id"]),
    )
    assert cross_org.status_code == 404
    unknown_enc = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, str(uuid4())),
    )
    assert unknown_enc.status_code == 404
    cross_identity = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(foreign_patient),
    )
    assert cross_identity.status_code == 404

    cancelled = await _open_encounter(db_client, clinician, patient_id)
    cancel = await db_client.post(
        f"/api/v1/clinical/encounters/{cancelled.json()['id']}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "CANCELLED"},
    )
    assert cancel.status_code == 200
    blocked_cancelled = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, cancelled.json()["id"]),
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
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, erroneous.json()["id"]),
    )
    assert blocked_eie_enc.status_code == 409

    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Ae",
            "family_name": "Source",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B7"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Ae", family="Survivor", birth="1982-02-02"),
    )
    source_encounter = await _open_encounter(db_client, clinician, source.json()["id"])
    historical = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(source.json()["id"], source_encounter.json()["id"]),
    )
    assert historical.status_code in {200, 201}
    historical_id = historical.json()["id"]
    assert historical.json()["patient_identity_id"] == source.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.7 historical adverse event",
            "evidence": merge_evidence("wave2b7-hist"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/adverse-events/{historical_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    rebound = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(source.json()["id"], source_encounter.json()["id"]),
    )
    assert rebound.status_code == 409
    created = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(source.json()["id"]),
    )
    assert created.json()["patient_identity_id"] == survivor.json()["id"]
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
    missing = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(str(uuid4())),
    )
    assert missing.status_code == 404


@requires_db
async def test_adverse_event_related_facts(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    other_registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=other.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    foreign_patient = await _active_patient(db_client, other_registrar)

    medication = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(patient_id),
    )
    assert medication.status_code in {200, 201}
    medication_id = medication.json()["id"]
    medication_status = medication.json()["status"]
    medication_version = medication.json()["version"]

    device = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(patient_id),
    )
    assert device.status_code in {200, 201}
    device_id = device.json()["id"]
    device_status = device.json()["status"]
    device_version = device.json()["version"]

    procedure = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id),
    )
    assert procedure.status_code in {200, 201}
    procedure_id = procedure.json()["id"]
    procedure_status = procedure.json()["status"]
    procedure_version = procedure.json()["version"]

    linked_med = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, medication_id=medication_id),
    )
    assert linked_med.status_code in {200, 201}
    assert linked_med.json()["medication_id"] == medication_id
    assert linked_med.json()["medical_device_id"] is None
    assert linked_med.json()["procedure_id"] is None

    linked_device = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, medical_device_id=device_id),
    )
    assert linked_device.status_code in {200, 201}
    assert linked_device.json()["medical_device_id"] == device_id

    linked_proc = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, procedure_id=procedure_id),
    )
    assert linked_proc.status_code in {200, 201}
    assert linked_proc.json()["procedure_id"] == procedure_id

    both = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, medication_id=medication_id, medical_device_id=device_id),
    )
    assert both.status_code == 422
    med_proc = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, medication_id=medication_id, procedure_id=procedure_id),
    )
    assert med_proc.status_code == 422
    device_proc = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, medical_device_id=device_id, procedure_id=procedure_id),
    )
    assert device_proc.status_code == 422

    other_med = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(other_patient),
    )
    mismatch = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, medication_id=other_med.json()["id"]),
    )
    assert mismatch.status_code == 409

    foreign_med = await db_client.post(
        "/api/v1/clinical/medications",
        headers=other.headers(purpose="TREATMENT"),
        json=_paracetamol(foreign_patient),
    )
    cross = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, medication_id=foreign_med.json()["id"]),
    )
    assert cross.status_code == 404
    assert "Paracetamol" not in cross.text

    missing_related = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, medication_id=str(uuid4())),
    )
    assert missing_related.status_code == 404

    eie_med = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(patient_id),
    )
    void_med = await db_client.post(
        f"/api/v1/clinical/medications/{eie_med.json()['id']}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert void_med.status_code == 200
    blocked_eie_related = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, medication_id=eie_med.json()["id"]),
    )
    assert blocked_eie_related.status_code == 409

    later_eie = await db_client.post(
        f"/api/v1/clinical/medications/{medication_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert later_eie.status_code == 200
    still_linked = await db_client.get(
        f"/api/v1/clinical/adverse-events/{linked_med.json()['id']}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert still_linked.json()["medication_id"] == medication_id
    assert still_linked.json()["status"] == "ACTIVE"

    retarget = await db_client.post(
        f"/api/v1/clinical/adverse-events/{linked_med.json()['id']}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_amend_body(severity="MODERATE"), "medication_id": device_id},
    )
    assert retarget.status_code == 200
    assert retarget.json()["medication_id"] == medication_id
    assert retarget.json()["medical_device_id"] is None

    unchanged_device = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unchanged_device.json()["status"] == device_status
    assert unchanged_device.json()["version"] == device_version
    unchanged_proc = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unchanged_proc.json()["status"] == procedure_status
    assert unchanged_proc.json()["version"] == procedure_version
    assert medication_status == "ACTIVE"
    assert medication_version == 1

    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE adverse_events SET medication_id = NULL WHERE id = :id"),
                    {"id": linked_med.json()["id"]},
                )
        with pytest.raises(Exception, match="related_fact_at_most_one|check constraint"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO adverse_events (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, severity, medication_id, medical_device_id,
                            status, recorded_at, version
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               category, code_system, code, severity, :med, :dev,
                               'ACTIVE', now(), 1
                        FROM adverse_events WHERE id = :id
                        """
                    ),
                    {
                        "id": linked_med.json()["id"],
                        "med": medication_id,
                        "dev": device_id,
                    },
                )


@requires_db
async def test_adverse_event_concurrency_facility_and_app_dml(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="treatment"),
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
        events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ADVERSE_EVENT_AMENDED'
                """
            ),
            {"id": event_id},
        )
        assert events.scalar_one() == 1
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
        assert "Hives after first dose" not in metadata
        assert "concurrent amend" not in metadata

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
    assert other.json()["version"] == 1
    async with db_engine.connect() as connection:
        eie_version = await connection.execute(
            text("SELECT version FROM adverse_events WHERE id = :id"),
            {"id": other_id},
        )
        assert eie_version.scalar_one() == 1
        eie_audit = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ADVERSE_EVENT_ENTERED_IN_ERROR'
                """
            ),
            {"id": other_id},
        )
        assert eie_audit.scalar_one() == 1

    race = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id, note="amend vs eie"),
    )
    race_id = race.json()["id"]

    async def amend_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/adverse-events/{race_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    async def void_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/adverse-events/{race_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    raced_left, raced_right = await asyncio.gather(amend_race(), void_race())
    codes = {raced_left.status_code, raced_right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status FROM adverse_events WHERE id = :id"),
            {"id": race_id},
        )
        assert row.scalar_one() == "ENTERED_IN_ERROR"
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ADVERSE_EVENT_ENTERED_IN_ERROR'
                """
            ),
            {"id": race_id},
        )
        amended_count = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ADVERSE_EVENT_AMENDED'
                """
            ),
            {"id": race_id},
        )
        assert eie.scalar_one() == 1
        assert amended_count.scalar_one() in {0, 1}

    in_scope = new_id()
    out_of_scope = new_id()
    async with db_engine.begin() as connection:
        for facility_id, code in ((in_scope, "AIN"), (out_of_scope, "AOUT")):
            await connection.execute(
                FacilityModel.__table__.insert().values(
                    id=facility_id,
                    organization_id=clinician.organization_id,
                    name=code,
                    code=code,
                    facility_type=FacilityType.HOSPITAL_SITE,
                    status=FacilityStatus.ACTIVE,
                )
            )
        role_id = (
            await connection.execute(
                select(RoleModel.id).where(RoleModel.code == RoleCode.CLINICIAN)
            )
        ).scalar_one()
        bound_user = new_id()
        subject = f"user-{bound_user}"
        await connection.execute(
            UserModel.__table__.insert().values(
                id=bound_user,
                subject=subject,
                display_name=subject,
                status=UserStatus.ACTIVE,
            )
        )
        await connection.execute(
            OrganizationMembershipModel.__table__.insert().values(
                id=new_id(),
                user_id=bound_user,
                organization_id=clinician.organization_id,
                facility_id=in_scope,
                role_id=role_id,
                status=MembershipStatus.ACTIVE,
            )
        )
    bound = SeededActor(bound_user, subject, clinician.organization_id, mint_token(sub=subject))
    allowed = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=_headers(bound, "TREATMENT", str(in_scope)),
    )
    assert allowed.status_code == 200
    denied = await db_client.get(
        f"/api/v1/clinical/adverse-events/{event_id}",
        headers=_headers(bound, "TREATMENT", str(out_of_scope)),
    )
    assert denied.status_code == 403
    assert "Anaphylaxis" not in denied.text

    async with db_engine.connect() as connection:
        provenance = await connection.execute(
            text("SELECT provenance_id FROM adverse_events WHERE id = :id"),
            {"id": event_id},
        )
        provenance_id = provenance.scalar_one()
        assert provenance_id is not None
        checks = await connection.execute(
            text(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'adverse_events'::regclass
                  AND contype = 'c'
                """
            )
        )
        names = {row[0] for row in checks}
        assert any(name.endswith("adverse_event_category") for name in names)
        assert any(name.endswith("adverse_event_severity") for name in names)
        assert any(name.endswith("adverse_event_status") for name in names)
        assert any(name.endswith("adverse_event_related_fact_at_most_one") for name in names)
        assert any(name.endswith("adverse_event_version_positive") for name in names)
        fks = await connection.execute(
            text(
                """
                SELECT constraint_name, delete_rule
                FROM information_schema.referential_constraints
                WHERE constraint_name LIKE 'fk_adverse_events_%'
                """
            )
        )
        rules = {row[0]: row[1] for row in fks}
        assert rules["fk_adverse_events_patient_identity_id"] == "RESTRICT"
        assert rules["fk_adverse_events_encounter_id"] == "RESTRICT"
        assert rules["fk_adverse_events_organization_id"] == "RESTRICT"
        assert rules["fk_adverse_events_facility_id"] == "RESTRICT"
        assert rules["fk_adverse_events_medication_id"] == "RESTRICT"
        assert rules["fk_adverse_events_medical_device_id"] == "RESTRICT"
        assert rules["fk_adverse_events_procedure_id"] == "RESTRICT"
        assert rules["fk_adverse_events_provenance_id"] == "RESTRICT"
        pk = await connection.execute(
            text(
                """
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'adverse_events' AND column_name = 'id'
                """
            )
        )
        assert pk.scalar_one() == "uuid"
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="foreign key|fk_adverse_events_provenance"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO adverse_events (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, severity, status, recorded_at, version,
                            provenance_id
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               category, code_system, code, severity, 'ACTIVE',
                               now(), 1, :bad
                        FROM adverse_events WHERE id = :id
                        """
                    ),
                    {"id": event_id, "bad": uuid4()},
                )
        with pytest.raises(Exception, match="insert-only|foreign key|fk_adverse_events_provenance"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM clinical_provenances WHERE id = :id"),
                    {"id": provenance_id},
                )
        with pytest.raises(Exception, match="invalid adverse event status transition"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE adverse_events SET status = 'ACTIVE' WHERE id = :id"),
                    {"id": event_id},
                )
        with pytest.raises(Exception, match="adverse_event_category|violates check"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO adverse_events (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, severity, status, recorded_at, version
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               'MEDICATION', code_system, code, severity, 'ACTIVE',
                               now(), 1
                        FROM adverse_events WHERE id = :id
                        """
                    ),
                    {"id": event_id},
                )
        with pytest.raises(Exception, match="adverse_event_severity|violates check"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO adverse_events (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, severity, status, recorded_at, version
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               category, code_system, code, 'LIFE_THREATENING', 'ACTIVE',
                               now(), 1
                        FROM adverse_events WHERE id = :id
                        """
                    ),
                    {"id": event_id},
                )
        with pytest.raises(Exception, match="adverse_event_status|violates check"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO adverse_events (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, severity, status, recorded_at, version
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               category, code_system, code, severity, 'CANCELLED',
                               now(), 1
                        FROM adverse_events WHERE id = :id
                        """
                    ),
                    {"id": event_id},
                )
        with pytest.raises(Exception, match="adverse_event_version_positive|violates check"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO adverse_events (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, severity, status, recorded_at, version
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               category, code_system, code, severity, 'ACTIVE',
                               now(), 0
                        FROM adverse_events WHERE id = :id
                        """
                    ),
                    {"id": event_id},
                )

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM adverse_events WHERE id = :id"),
                        {"id": event_id},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            "UPDATE adverse_events SET code_display = 'Anaphylactic shock' "
                            "WHERE id = :id"
                        ),
                        {"id": event_id},
                    )
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE adverse_events"))
    finally:
        await engine.dispose()
