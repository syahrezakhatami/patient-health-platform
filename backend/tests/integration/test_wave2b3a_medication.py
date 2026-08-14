import asyncio
import os
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter

pytestmark = [pytest.mark.integration]

ATC = "http://www.whocc.no/atc"
APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


def _paracetamol(
    patient_id: str,
    encounter_id: str | None = None,
    *,
    dose: float | None = 500,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "patient_identity_id": patient_id,
        "category": "PRESCRIBED",
        "code": {"system": ATC, "code": "N02BE01", "display": "Paracetamol"},
        "route": "ORAL",
    }
    if dose is not None:
        payload["dose_numeric"] = dose
        payload["dose_unit"] = "mg"
    if encounter_id is not None:
        payload["encounter_id"] = encounter_id
    return payload


@requires_db
async def test_medication_lifecycle_identity_and_authorization(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    auditor = await seed_actor(
        db_engine, role_code=RoleCode.AUDITOR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]

    invalid = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_paracetamol(patient_id, dose=None), "dose_unit": "mg"},
    )
    assert invalid.status_code == 422

    created = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(patient_id, encounter_id),
    )
    assert created.status_code in {200, 201}
    body = created.json()
    assert body["status"] == "ACTIVE"
    assert body["version"] == 1
    assert body["category"] == "PRESCRIBED"
    assert float(body["dose_numeric"]) == 500
    medication_id = body["id"]

    denied = await db_client.post(
        "/api/v1/clinical/medications",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_paracetamol(patient_id),
    )
    assert denied.status_code == 403

    listed = await db_client.get(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert listed.status_code == 200
    assert medication_id in {item["id"] for item in listed.json()}

    auditor_read = await db_client.get(
        f"/api/v1/clinical/medications/{medication_id}",
        headers=auditor.headers(purpose="AUDIT"),
    )
    assert auditor_read.status_code == 200

    stopped = await db_client.post(
        f"/api/v1/clinical/medications/{medication_id}/stop",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "STOPPED"
    assert stopped.json()["stopped_at"] is not None
    assert stopped.json()["version"] == 2
    noop = await db_client.post(
        f"/api/v1/clinical/medications/{medication_id}/stop",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert noop.status_code == 409

    voided = await db_client.post(
        f"/api/v1/clinical/medications/{medication_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    blocked = await db_client.post(
        f"/api/v1/clinical/medications/{medication_id}/stop",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked.status_code == 409
    blocked_eie = await db_client.post(
        f"/api/v1/clinical/medications/{medication_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_eie.status_code == 409

    cross = await db_client.get(
        f"/api/v1/clinical/medications/{medication_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "sqlalchemy" not in cross.text.lower()
    assert "N02BE01" not in cross.text
    assert "Paracetamol" not in cross.text
    unknown = await db_client.get(
        f"/api/v1/clinical/medications/{uuid4()}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unknown.status_code == 404
    deleted = await db_client.delete(
        f"/api/v1/clinical/medications/{medication_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
    missing_purpose = await db_client.get(
        f"/api/v1/clinical/medications/{medication_id}",
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
    )
    assert missing_purpose.status_code == 422

    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE medications SET patient_identity_id = :pid WHERE id = :id"),
                    {"id": medication_id, "pid": uuid4()},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE medications SET dose_numeric = 1000 WHERE id = :id"),
                    {"id": medication_id},
                )
        with pytest.raises(Exception, match="cannot be deleted"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM medications WHERE id = :id"),
                    {"id": medication_id},
                )
        provenance = await connection.execute(
            text(
                """
                SELECT subject_type FROM clinical_provenances
                WHERE id = (SELECT provenance_id FROM medications WHERE id = :id)
                """
            ),
            {"id": medication_id},
        )
        assert provenance.scalar_one() == "MEDICATION"
        fk = await connection.execute(
            text(
                """
                SELECT delete_rule FROM information_schema.referential_constraints
                WHERE constraint_name = 'fk_medications_provenance_id'
                """
            )
        )
        assert fk.scalar_one() == "RESTRICT"
        audit = await connection.execute(
            text("SELECT action, metadata::text FROM audit_events WHERE resource_id = :id"),
            {"id": medication_id},
        )
        rows = list(audit)
        actions = {row[0] for row in rows}
        assert "MEDICATION_CREATED" in actions
        assert "MEDICATION_STOPPED" in actions
        assert "MEDICATION_ENTERED_IN_ERROR" in actions
        assert all("N02BE01" not in (row[1] or "") for row in rows)
        assert all("Paracetamol" not in (row[1] or "") for row in rows)
        assert all("500" not in (row[1] or "") for row in rows)
        later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'allergies','consents','fhir_medication_requests',
                    'prescriptions','fhir_observations'
                  )
                """
            )
        )
        assert later.scalar_one() == 0
        present = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'medications'
                """
            )
        )
        assert present.scalar_one() == 1


@requires_db
async def test_anonymous_merged_and_encounter_medication_binding(db_client, db_engine) -> None:
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
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(anonymous_id),
    )
    assert blocked.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    allowed = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(anonymous_id, emer.json()["id"]),
    )
    assert allowed.status_code in {200, 201}

    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    foreign_patient = await _active_patient(db_client, other_registrar)
    mismatch = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(
            patient_id, (await _open_encounter(db_client, clinician, other_patient)).json()["id"]
        ),
    )
    assert mismatch.status_code == 409
    foreign = await _open_encounter(db_client, other, foreign_patient)
    cross_org = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(patient_id, foreign.json()["id"]),
    )
    assert cross_org.status_code == 404
    unknown_enc = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(patient_id, str(uuid4())),
    )
    assert unknown_enc.status_code == 404

    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Med",
            "family_name": "Source",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B3A"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Med", family="Survivor", birth="1982-02-02"),
    )
    historical = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(source.json()["id"]),
    )
    assert historical.status_code in {200, 201}
    historical_id = historical.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.3a historical medication",
            "evidence": merge_evidence("wave2b3a-hist"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/medications/{historical_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    created = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(source.json()["id"]),
    )
    assert created.json()["patient_identity_id"] == survivor.json()["id"]
    retired = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    rejected = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(retired),
    )
    assert rejected.status_code == 409
    missing = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(str(uuid4())),
    )
    assert missing.status_code == 404


@requires_db
async def test_medication_concurrency_and_app_dml_delete(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(patient_id, dose=250),
    )
    medication_id = created.json()["id"]

    async def stop() -> object:
        return await db_client.post(
            f"/api/v1/clinical/medications/{medication_id}/stop",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    first, second = await asyncio.gather(stop(), stop())
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'MEDICATION_STOPPED'
                """
            ),
            {"id": medication_id},
        )
        assert events.scalar_one() == 1

    other = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(patient_id, dose=100),
    )
    other_id = other.json()["id"]

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/medications/{other_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(void(), void())
    assert sorted([left.status_code, right.status_code]) == [200, 409]
    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM medications WHERE id = :id"),
                        {"id": medication_id},
                    )
    finally:
        await engine.dispose()
