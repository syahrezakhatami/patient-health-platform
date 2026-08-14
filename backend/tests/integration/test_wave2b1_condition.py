import asyncio
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from sqlalchemy import text
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter

pytestmark = [pytest.mark.integration]

ICD10 = "http://hl7.org/fhir/sid/icd-10"


def _pneumonia(patient_id: str, encounter_id: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "patient_identity_id": patient_id,
        "category": "ENCOUNTER_DIAGNOSIS" if encounter_id else "PROBLEM_LIST_ITEM",
        "code": {"system": ICD10, "code": "J18.9", "display": "Pneumonia, unspecified"},
    }
    if encounter_id is not None:
        payload["encounter_id"] = encounter_id
    return payload


@requires_db
async def test_condition_lifecycle_identity_and_authorization(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]

    missing_code_encounter = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json={
            "patient_identity_id": patient_id,
            "category": "ENCOUNTER_DIAGNOSIS",
            "code": {"system": ICD10, "code": "J18.9", "display": "Pneumonia, unspecified"},
        },
    )
    assert missing_code_encounter.status_code == 422

    problem = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    assert problem.status_code in {200, 201}
    assert problem.json()["category"] == "PROBLEM_LIST_ITEM"
    assert problem.json()["clinical_status"] == "ACTIVE"
    assert problem.json()["verification_status"] == "CONFIRMED"
    problem_id = problem.json()["id"]

    diagnosis = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id, encounter_id),
    )
    assert diagnosis.status_code in {200, 201}
    assert diagnosis.json()["encounter_id"] == encounter_id
    condition_id = diagnosis.json()["id"]

    denied = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id, encounter_id),
    )
    assert denied.status_code == 403

    listed = await db_client.get(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} >= {problem_id, condition_id}

    resolved = await db_client.post(
        f"/api/v1/clinical/conditions/{condition_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"clinical_status": "RESOLVED"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["clinical_status"] == "RESOLVED"

    illegal = await db_client.post(
        f"/api/v1/clinical/conditions/{condition_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"clinical_status": "INACTIVE"},
    )
    assert illegal.status_code == 409

    voided = await db_client.post(
        f"/api/v1/clinical/conditions/{condition_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["verification_status"] == "ENTERED_IN_ERROR"
    blocked = await db_client.post(
        f"/api/v1/clinical/conditions/{condition_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"clinical_status": "ACTIVE"},
    )
    assert blocked.status_code == 409

    cross = await db_client.get(
        f"/api/v1/clinical/conditions/{condition_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "sqlalchemy" not in cross.text.lower()
    assert "J18.9" not in cross.text
    unknown = await db_client.get(
        f"/api/v1/clinical/conditions/{uuid4()}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unknown.status_code == 404

    missing_purpose = await db_client.get(
        f"/api/v1/clinical/conditions/{problem_id}",
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
    )
    assert missing_purpose.status_code == 422

    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="immutable|cannot"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE conditions SET code = 'A00.0' WHERE id = :id"),
                    {"id": condition_id},
                )
        with pytest.raises(Exception, match="cannot be deleted"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM conditions WHERE id = :id"), {"id": condition_id}
                )
        audit = await connection.execute(
            text(
                """
                SELECT action, metadata::text FROM audit_events
                WHERE resource_id = :id
                """
            ),
            {"id": condition_id},
        )
        rows = list(audit)
        actions = {row[0] for row in rows}
        assert "CONDITION_CREATED" in actions
        assert "CONDITION_ENTERED_IN_ERROR" in actions
        assert all("Pneumonia" not in (row[1] or "") for row in rows)
        later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'diagnoses','medications','observations','laboratory_results',
                    'allergies','fhir_conditions'
                  )
                """
            )
        )
        assert later.scalar_one() == 0


@requires_db
async def test_anonymous_and_merged_condition_binding(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=registrar.headers(purpose="EMERGENCY"),
        json={},
    )
    anonymous_id = anonymous.json()["id"]
    blocked_list = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(anonymous_id),
    )
    assert blocked_list.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    assert emer.status_code in {200, 201}
    allowed = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(anonymous_id, emer.json()["id"]),
    )
    assert allowed.status_code in {200, 201}
    assert allowed.json()["patient_identity_id"] == anonymous_id

    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Cond",
            "family_name": "Source",
            "birth_date": "1980-01-01",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B1"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Cond", family="Survivor", birth="1980-01-01"),
    )
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.1 identity binding",
            "evidence": merge_evidence("wave2b1-bind"),
        },
    )
    assert merged.status_code in {200, 201}
    created = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(source.json()["id"]),
    )
    assert created.status_code in {200, 201}
    assert created.json()["patient_identity_id"] == survivor.json()["id"]

    retired = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    rejected = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(retired),
    )
    assert rejected.status_code == 409
    missing = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(str(uuid4())),
    )
    assert missing.status_code == 404


@requires_db
async def test_concurrent_condition_status_change(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    condition_id = created.json()["id"]

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/conditions/{condition_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    first, second = await asyncio.gather(void(), void())
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409]
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT verification_status FROM conditions WHERE id = :id"),
            {"id": condition_id},
        )
        assert row.scalar_one() == "ENTERED_IN_ERROR"
        events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CONDITION_ENTERED_IN_ERROR'
                """
            ),
            {"id": condition_id},
        )
        assert events.scalar_one() == 1
