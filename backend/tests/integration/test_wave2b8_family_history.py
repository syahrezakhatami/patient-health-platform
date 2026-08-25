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
from tests.integration.test_wave2b1_condition import _pneumonia
from tests.integration.test_wave2b3c_consent import _consent
from tests.integration.test_wave15_hardening import _headers

pytestmark = [pytest.mark.integration]

SNOMED = "http://snomed.info/sct"
APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


def _history(
    patient_id: str,
    encounter_id: str | None = None,
    *,
    note: str | None = "Mother diagnosed at 42",
    category: str = "DOCUMENTED",
    relationship: str = "PARENT",
    occurrence_at: str | None = None,
    code: str = "254837009",
    display: str = "Breast cancer",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "patient_identity_id": patient_id,
        "relationship": relationship,
        "category": category,
        "code": {"system": SNOMED, "code": code, "display": display},
    }
    if note is not None:
        payload["note_text"] = note
    if occurrence_at is not None:
        payload["occurrence_at"] = occurrence_at
    if encounter_id is not None:
        payload["encounter_id"] = encounter_id
    return payload


def _amend_body(
    *, note: str | None = "Corrected note", occurrence_at: str | None = None
) -> dict[str, object]:
    payload: dict[str, object] = {"note_text": note}
    if occurrence_at is not None:
        payload["occurrence_at"] = occurrence_at
    return payload


def test_family_history_lock_is_select_for_update_not_redis() -> None:
    lock_source = inspect.getsource(ClinicalRepository.get_family_history_for_update)
    amend_source = inspect.getsource(ClinicalService.amend_family_history)
    eie_source = inspect.getsource(ClinicalService.mark_family_history_entered_in_error)
    assert "with_for_update" in lock_source
    assert "redis" not in amend_source.lower()
    assert "redis" not in eie_source.lower()


@requires_db
async def test_family_history_lifecycle_identity_and_authorization(db_client, db_engine) -> None:
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
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_history(patient_id), "category": "NOT_A_CATEGORY"},
    )
    assert invalid.status_code == 422
    invalid_rel = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_history(patient_id), "relationship": "MOTHER"},
    )
    assert invalid_rel.status_code == 422
    invalid_code = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_history(patient_id), "code": {"system": "", "code": "254837009"}},
    )
    assert invalid_code.status_code == 422

    created = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id, encounter_id),
    )
    assert created.status_code in {200, 201}
    body = created.json()
    assert body["status"] == "ACTIVE"
    assert body["version"] == 1
    assert body["category"] == "DOCUMENTED"
    assert body["relationship"] == "PARENT"
    assert body["code"]["code"] == "254837009"
    assert "condition_id" not in body
    history_id = body["id"]

    denied = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_history(patient_id),
    )
    assert denied.status_code == 403
    assert "Breast cancer" not in denied.text
    assert "Mother diagnosed at 42" not in denied.text
    officer_denied = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=officer.headers(purpose="TREATMENT"),
        json=_history(patient_id),
    )
    assert officer_denied.status_code == 403
    registrar_read = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=registrar.headers(purpose="TREATMENT"),
    )
    assert registrar_read.status_code == 403
    officer_read = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=officer.headers(purpose="TREATMENT"),
    )
    assert officer_read.status_code == 403

    listed = await db_client.get(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert listed.status_code == 200
    assert history_id in {item["id"] for item in listed.json()}

    auditor_read = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=auditor.headers(purpose="AUDIT"),
    )
    assert auditor_read.status_code == 200
    admin_create = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_history(patient_id),
    )
    assert admin_create.status_code == 403
    admin_read = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=org_admin.headers(purpose="TREATMENT"),
    )
    assert admin_read.status_code == 200
    platform_created = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=platform.headers(purpose="TREATMENT"),
        json=_history(patient_id, relationship="SIBLING"),
    )
    assert platform_created.status_code in {200, 201}
    platform_read = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=platform.headers(purpose="TREATMENT"),
    )
    assert platform_read.status_code == 200

    consent = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id),
    )
    assert consent.status_code in {200, 201}
    registrar_after_consent = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_history(patient_id, note="denied payload"),
    )
    assert registrar_after_consent.status_code == 403
    assert "denied payload" not in registrar_after_consent.text

    amended = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(),
    )
    assert amended.status_code == 200
    assert amended.json()["status"] == "AMENDED"
    assert amended.json()["note_text"] == "Corrected note"
    assert amended.json()["version"] == 2
    assert amended.json()["relationship"] == "PARENT"
    noop = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(),
    )
    assert noop.status_code == 409

    voided = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    assert voided.json()["version"] == 2
    blocked = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="after eie"),
    )
    assert blocked.status_code == 409
    blocked_eie = await db_client.post(
        f"/api/v1/clinical/family-histories/{history_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_eie.status_code == 409

    cross = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "sqlalchemy" not in cross.text.lower()
    assert "254837009" not in cross.text
    assert "Breast cancer" not in cross.text
    unknown = await db_client.get(
        f"/api/v1/clinical/family-histories/{uuid4()}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unknown.status_code == 404
    deleted = await db_client.delete(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
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
    missing_purpose = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
    )
    assert missing_purpose.status_code == 422
    invalid_purpose = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=clinician.headers(purpose="NOT_A_PURPOSE"),
    )
    assert invalid_purpose.status_code == 422
    unauthenticated = await db_client.get(f"/api/v1/clinical/family-histories/{history_id}")
    assert unauthenticated.status_code == 401
    unauthenticated_post = await db_client.post(
        "/api/v1/clinical/family-histories",
        json=_history(patient_id),
    )
    assert unauthenticated_post.status_code == 401
    unprovisioned = mint_token(sub="nobody-family-history")
    denied_jwt = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
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
                    text("UPDATE family_histories SET patient_identity_id = :pid WHERE id = :id"),
                    {"id": history_id, "pid": uuid4()},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE family_histories SET relationship = 'SIBLING' WHERE id = :id"),
                    {"id": history_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE family_histories SET code = 'changed' WHERE id = :id"),
                    {"id": history_id},
                )
        with pytest.raises(Exception, match="cannot be deleted"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM family_histories WHERE id = :id"),
                    {"id": history_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE family_histories SET status = 'ACTIVE' WHERE id = :id"),
                    {"id": history_id},
                )
        platform_id = platform_created.json()["id"]
        async with connection.begin():
            await connection.execute(
                text("UPDATE family_histories SET status = 'AMENDED' WHERE id = :id"),
                {"id": platform_id},
            )
        with pytest.raises(Exception, match="invalid family history status transition"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE family_histories SET status = 'ACTIVE' WHERE id = :id"),
                    {"id": platform_id},
                )
        provenance = await connection.execute(
            text(
                """
                SELECT subject_type FROM clinical_provenances
                WHERE id = (SELECT provenance_id FROM family_histories WHERE id = :id)
                """
            ),
            {"id": history_id},
        )
        assert provenance.scalar_one() == "FAMILY_HISTORY"
        fk = await connection.execute(
            text(
                """
                SELECT delete_rule FROM information_schema.referential_constraints
                WHERE constraint_name = 'fk_family_histories_provenance_id'
                """
            )
        )
        assert fk.scalar_one() == "RESTRICT"
        audit = await connection.execute(
            text("SELECT action, metadata::text FROM audit_events WHERE resource_id = :id"),
            {"id": history_id},
        )
        rows = list(audit)
        actions = {row[0] for row in rows}
        assert "FAMILY_HISTORY_CREATED" in actions
        assert "FAMILY_HISTORY_AMENDED" in actions
        assert "FAMILY_HISTORY_ENTERED_IN_ERROR" in actions
        assert all("Breast cancer" not in (row[1] or "") for row in rows)
        assert all("Mother diagnosed at 42" not in (row[1] or "") for row in rows)
        assert all("254837009" not in (row[1] or "") for row in rows)
        later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'fhir_family_member_histories','care_plans','vital_signs',
                    'patient_histories','diagnoses','family_conditions'
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
                    'family_histories','adverse_events','conditions'
                  )
                """
            )
        )
        assert present.scalar_one() == 3
        no_condition_fk = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_name = 'family_histories' AND column_name = 'condition_id'
                """
            )
        )
        assert no_condition_fk.scalar_one() == 0


@requires_db
async def test_anonymous_merged_and_encounter_family_history_binding(db_client, db_engine) -> None:
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
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(anonymous_id),
    )
    assert blocked.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE encounters SET encounter_class = 'AMB' WHERE id = :id"),
            {"id": emer.json()["id"]},
        )
    blocked_amb = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(anonymous_id, emer.json()["id"]),
    )
    assert blocked_amb.status_code == 409
    restored = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    allowed = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(anonymous_id, restored.json()["id"]),
    )
    assert allowed.status_code in {200, 201}

    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    foreign_patient = await _active_patient(db_client, other_registrar)
    mismatch = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(
            patient_id, (await _open_encounter(db_client, clinician, other_patient)).json()["id"]
        ),
    )
    assert mismatch.status_code == 409
    foreign = await _open_encounter(db_client, other, foreign_patient)
    cross_org = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id, foreign.json()["id"]),
    )
    assert cross_org.status_code == 404
    unknown_enc = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id, str(uuid4())),
    )
    assert unknown_enc.status_code == 404
    cross_identity = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(foreign_patient),
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
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id, cancelled.json()["id"]),
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
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id, erroneous.json()["id"]),
    )
    assert blocked_eie_enc.status_code == 409

    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Fh",
            "family_name": "Source",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B8"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Fh", family="Survivor", birth="1982-02-02"),
    )
    source_encounter = await _open_encounter(db_client, clinician, source.json()["id"])
    historical = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(source.json()["id"], source_encounter.json()["id"]),
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
            "reason": "Wave 2B.8 historical family history",
            "evidence": merge_evidence("wave2b8-hist"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/family-histories/{historical_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    rebound = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(source.json()["id"], source_encounter.json()["id"]),
    )
    assert rebound.status_code == 409
    created = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(source.json()["id"]),
    )
    assert created.json()["patient_identity_id"] == survivor.json()["id"]
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
    missing = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(str(uuid4())),
    )
    assert missing.status_code == 404


@requires_db
async def test_family_history_does_not_become_condition_or_patient_history(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    condition = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    assert condition.status_code in {200, 201}
    condition_id = condition.json()["id"]
    condition_clinical = condition.json()["clinical_status"]
    condition_verification = condition.json()["verification_status"]
    family = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id, code="J18.9", display="Pneumonia, unspecified"),
    )
    assert family.status_code in {200, 201}
    assert family.json()["id"] != condition_id
    assert "condition_id" not in family.json()
    after = await db_client.get(
        f"/api/v1/clinical/conditions/{condition_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert after.json()["clinical_status"] == condition_clinical
    assert after.json()["verification_status"] == condition_verification
    listed_conditions = await db_client.get(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert condition_id in {item["id"] for item in listed_conditions.json()}
    assert family.json()["id"] not in {item["id"] for item in listed_conditions.json()}


@requires_db
async def test_family_history_concurrency_facility_and_app_dml(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="treatment"),
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
        events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'FAMILY_HISTORY_AMENDED'
                """
            ),
            {"id": history_id},
        )
        assert events.scalar_one() == 1
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
        assert "PARENT" in metadata
        assert "Mother diagnosed at 42" not in metadata
        assert "concurrent amend" not in metadata
        assert "Breast cancer" not in metadata

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
    assert other.json()["version"] == 1
    async with db_engine.connect() as connection:
        eie_version = await connection.execute(
            text("SELECT version FROM family_histories WHERE id = :id"),
            {"id": other_id},
        )
        assert eie_version.scalar_one() == 1
        eie_audit = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'FAMILY_HISTORY_ENTERED_IN_ERROR'
                """
            ),
            {"id": other_id},
        )
        assert eie_audit.scalar_one() == 1

    race = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id, note="amend vs eie"),
    )
    race_id = race.json()["id"]

    async def amend_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/family-histories/{race_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    async def void_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/family-histories/{race_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    raced_left, raced_right = await asyncio.gather(amend_race(), void_race())
    codes = {raced_left.status_code, raced_right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status FROM family_histories WHERE id = :id"),
            {"id": race_id},
        )
        assert row.scalar_one() == "ENTERED_IN_ERROR"
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'FAMILY_HISTORY_ENTERED_IN_ERROR'
                """
            ),
            {"id": race_id},
        )
        amended_count = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'FAMILY_HISTORY_AMENDED'
                """
            ),
            {"id": race_id},
        )
        assert eie.scalar_one() == 1
        assert amended_count.scalar_one() in {0, 1}

    in_scope = new_id()
    out_of_scope = new_id()
    async with db_engine.begin() as connection:
        for facility_id, code in ((in_scope, "FIN"), (out_of_scope, "FOUT")):
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
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=_headers(bound, "TREATMENT", str(in_scope)),
    )
    assert allowed.status_code == 200
    denied = await db_client.get(
        f"/api/v1/clinical/family-histories/{history_id}",
        headers=_headers(bound, "TREATMENT", str(out_of_scope)),
    )
    assert denied.status_code == 403
    assert "Breast cancer" not in denied.text

    async with db_engine.connect() as connection:
        provenance = await connection.execute(
            text("SELECT provenance_id FROM family_histories WHERE id = :id"),
            {"id": history_id},
        )
        provenance_id = provenance.scalar_one()
        assert provenance_id is not None
        checks = await connection.execute(
            text(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'family_histories'::regclass
                  AND contype = 'c'
                """
            )
        )
        names = {row[0] for row in checks}
        assert any(name.endswith("family_history_relationship") for name in names)
        assert any(name.endswith("family_history_category") for name in names)
        assert any(name.endswith("family_history_status") for name in names)
        assert any(name.endswith("family_history_version_positive") for name in names)
        fks = await connection.execute(
            text(
                """
                SELECT constraint_name, delete_rule
                FROM information_schema.referential_constraints
                WHERE constraint_name LIKE 'fk_family_histories_%'
                """
            )
        )
        rules = {row[0]: row[1] for row in fks}
        assert rules["fk_family_histories_patient_identity_id"] == "RESTRICT"
        assert rules["fk_family_histories_encounter_id"] == "RESTRICT"
        assert rules["fk_family_histories_organization_id"] == "RESTRICT"
        assert rules["fk_family_histories_facility_id"] == "RESTRICT"
        assert rules["fk_family_histories_provenance_id"] == "RESTRICT"
        pk = await connection.execute(
            text(
                """
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'family_histories' AND column_name = 'id'
                """
            )
        )
        assert pk.scalar_one() == "uuid"
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="foreign key|fk_family_histories_provenance"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO family_histories (
                            id, patient_identity_id, organization_id, relationship, category,
                            code_system, code, status, recorded_at, version, provenance_id
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               relationship, category, code_system, code, 'ACTIVE',
                               now(), 1, :bad
                        FROM family_histories WHERE id = :id
                        """
                    ),
                    {"id": history_id, "bad": uuid4()},
                )
        with pytest.raises(
            Exception, match="insert-only|foreign key|fk_family_histories_provenance"
        ):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM clinical_provenances WHERE id = :id"),
                    {"id": provenance_id},
                )
        with pytest.raises(Exception, match="family_history_relationship|violates check"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO family_histories (
                            id, patient_identity_id, organization_id, relationship, category,
                            code_system, code, status, recorded_at, version
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               'MOTHER', category, code_system, code, 'ACTIVE',
                               now(), 1
                        FROM family_histories WHERE id = :id
                        """
                    ),
                    {"id": history_id},
                )
        with pytest.raises(Exception, match="family_history_category|violates check"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO family_histories (
                            id, patient_identity_id, organization_id, relationship, category,
                            code_system, code, status, recorded_at, version
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               relationship, 'GENETIC', code_system, code, 'ACTIVE',
                               now(), 1
                        FROM family_histories WHERE id = :id
                        """
                    ),
                    {"id": history_id},
                )
        with pytest.raises(Exception, match="family_history_status|violates check"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO family_histories (
                            id, patient_identity_id, organization_id, relationship, category,
                            code_system, code, status, recorded_at, version
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               relationship, category, code_system, code, 'STOPPED',
                               now(), 1
                        FROM family_histories WHERE id = :id
                        """
                    ),
                    {"id": history_id},
                )
        with pytest.raises(Exception, match="family_history_version_positive|violates check"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO family_histories (
                            id, patient_identity_id, organization_id, relationship, category,
                            code_system, code, status, recorded_at, version
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               relationship, category, code_system, code, 'ACTIVE',
                               now(), 0
                        FROM family_histories WHERE id = :id
                        """
                    ),
                    {"id": history_id},
                )

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            readable = await connection.execute(
                text("SELECT count(*) FROM family_histories WHERE id = :id"),
                {"id": history_id},
            )
            assert readable.scalar_one() == 1
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM family_histories WHERE id = :id"),
                        {"id": history_id},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            "UPDATE family_histories SET code_display = 'Malignant neoplasm' "
                            "WHERE id = :id"
                        ),
                        {"id": history_id},
                    )
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE family_histories"))
    finally:
        await engine.dispose()
