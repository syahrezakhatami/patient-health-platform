from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from sqlalchemy import text
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_wave1_mpi import _identity_payload, unique_nik

pytestmark = [pytest.mark.integration]


@requires_db
async def test_emergency_encounter_and_note_lifecycle(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    created = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=registrar.headers(purpose="EMERGENCY"),
        json={},
    )
    assert created.status_code in {200, 201}
    patient_id = created.json()["id"]
    encounter = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"patient_identity_id": patient_id, "encounter_class": "EMER"},
    )
    assert encounter.status_code in {200, 201}
    body = encounter.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["patient_identity_id"] == patient_id
    assert body["display_label"].startswith("ENC-")
    encounter_id = body["id"]

    note = await db_client.post(
        "/api/v1/clinical/notes",
        headers=clinician.headers(purpose="TREATMENT"),
        json={
            "encounter_id": encounter_id,
            "note_type": "ED",
            "body_text": "Anonymous trauma assessment. Airway clear.",
        },
    )
    assert note.status_code in {200, 201}
    assert note.json()["record_status"] == "DRAFT"
    note_id = note.json()["id"]

    updated = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"body_text": "Anonymous trauma assessment. Airway clear. IV started."},
    )
    assert updated.status_code == 200
    finalized = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}/finalize",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert finalized.status_code == 200
    assert finalized.json()["record_status"] == "FINAL"
    blocked = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"body_text": "should not overwrite final"},
    )
    assert blocked.status_code == 409

    listed = await db_client.get(
        "/api/v1/clinical/encounters",
        headers=clinician.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == encounter_id

    async with db_engine.connect() as connection:
        audit = await connection.execute(
            text("SELECT action FROM audit_events WHERE patient_id = :id"),
            {"id": patient_id},
        )
        actions = {row[0] for row in audit}
        assert "ENCOUNTER_CREATED" in actions
        assert "CLINICAL_NOTE_FINALIZED" in actions
        clinical_tables = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                        'diagnoses','allergies',
                        'fhir_encounters','fhir_patients'
                  )
                """
            )
        )
        assert clinical_tables.scalar_one() == 0


@requires_db
async def test_clinical_authorization_and_cross_org(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    patient_id = created.json()["id"]
    encounter = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"patient_identity_id": patient_id, "encounter_class": "AMB"},
    )
    encounter_id = encounter.json()["id"]
    denied_note = await db_client.post(
        "/api/v1/clinical/notes",
        headers=registrar.headers(purpose="TREATMENT"),
        json={"encounter_id": encounter_id, "note_type": "PROGRESS", "body_text": "not allowed"},
    )
    assert denied_note.status_code == 403
    missing_purpose = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
    )
    assert missing_purpose.status_code == 422
    cross = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    unknown = await db_client.get(
        f"/api/v1/clinical/encounters/{uuid4()}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unknown.status_code == 404
    assert "sqlalchemy" not in unknown.text.lower()
