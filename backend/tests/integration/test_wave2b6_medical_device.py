import asyncio
import os
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.infrastructure.models import OrganizationMembershipModel, RoleModel, UserModel
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel
from app.shared.types.ids import new_id
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import mint_token
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.db_privileges import PROVENANCE_DELETE_DENIED
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave15_hardening import _headers

pytestmark = [pytest.mark.integration]

SNOMED = "http://snomed.info/sct"
APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


def _device(
    patient_id: str,
    encounter_id: str | None = None,
    *,
    note: str | None = "Implanted 2019",
    category: str = "DOCUMENTED",
    association_status: str | None = None,
    occurrence_at: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "patient_identity_id": patient_id,
        "category": category,
        "code": {"system": SNOMED, "code": "14106009", "display": "Cardiac pacemaker"},
    }
    if note is not None:
        payload["note_text"] = note
    if association_status is not None:
        payload["association_status"] = association_status
    if occurrence_at is not None:
        payload["occurrence_at"] = occurrence_at
    if encounter_id is not None:
        payload["encounter_id"] = encounter_id
    return payload


def _amend_body(
    *,
    note: str | None = "Corrected note",
    association_status: str | None = None,
    occurrence_at: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"note_text": note}
    if association_status is not None:
        payload["association_status"] = association_status
    if occurrence_at is not None:
        payload["occurrence_at"] = occurrence_at
    return payload


@requires_db
async def test_medical_device_lifecycle_identity_and_authorization(db_client, db_engine) -> None:
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
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_device(patient_id), "category": "NOT_A_CATEGORY"},
    )
    assert invalid.status_code == 422
    invalid_code = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_device(patient_id), "code": {"system": "", "code": "14106009"}},
    )
    assert invalid_code.status_code == 422
    invalid_association = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_device(patient_id), "association_status": "RETIRED"},
    )
    assert invalid_association.status_code == 422

    created = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(patient_id, encounter_id),
    )
    assert created.status_code in {200, 201}
    body = created.json()
    assert body["status"] == "ACTIVE"
    assert body["version"] == 1
    assert body["category"] == "DOCUMENTED"
    assert body["association_status"] == "IN_USE"
    device_id = body["id"]

    denied = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_device(patient_id),
    )
    assert denied.status_code == 403
    assert "Cardiac pacemaker" not in denied.text
    assert "Implanted 2019" not in denied.text
    officer_denied = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=officer.headers(purpose="TREATMENT"),
        json=_device(patient_id),
    )
    assert officer_denied.status_code == 403
    registrar_read = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=registrar.headers(purpose="TREATMENT"),
    )
    assert registrar_read.status_code == 403
    officer_read = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=officer.headers(purpose="TREATMENT"),
    )
    assert officer_read.status_code == 403

    listed = await db_client.get(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert listed.status_code == 200
    assert device_id in {item["id"] for item in listed.json()}

    auditor_read = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=auditor.headers(purpose="AUDIT"),
    )
    assert auditor_read.status_code == 200
    admin_create = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_device(patient_id),
    )
    assert admin_create.status_code == 403
    admin_read = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=org_admin.headers(purpose="TREATMENT"),
    )
    assert admin_read.status_code == 200
    platform_read = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=platform.headers(purpose="TREATMENT"),
    )
    assert platform_read.status_code == 403

    amended = await db_client.post(
        f"/api/v1/clinical/medical-devices/{device_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(association_status="NO_LONGER_USED"),
    )
    assert amended.status_code == 200
    assert amended.json()["status"] == "AMENDED"
    assert amended.json()["note_text"] == "Corrected note"
    assert amended.json()["association_status"] == "NO_LONGER_USED"
    assert amended.json()["version"] == 2
    noop = await db_client.post(
        f"/api/v1/clinical/medical-devices/{device_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(association_status="NO_LONGER_USED"),
    )
    assert noop.status_code == 409

    voided = await db_client.post(
        f"/api/v1/clinical/medical-devices/{device_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    assert voided.json()["version"] == 2
    blocked = await db_client.post(
        f"/api/v1/clinical/medical-devices/{device_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(note="after eie"),
    )
    assert blocked.status_code == 409
    blocked_eie = await db_client.post(
        f"/api/v1/clinical/medical-devices/{device_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_eie.status_code == 409

    cross = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "sqlalchemy" not in cross.text.lower()
    assert "14106009" not in cross.text
    assert "Cardiac pacemaker" not in cross.text
    unknown = await db_client.get(
        f"/api/v1/clinical/medical-devices/{uuid4()}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unknown.status_code == 404
    deleted = await db_client.delete(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
    put = await db_client.put(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={},
    )
    assert put.status_code == 405
    patch = await db_client.patch(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"note_text": "patched"},
    )
    assert patch.status_code == 405
    v2 = await db_client.get(
        f"/api/v2/clinical/medical-devices/{device_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert v2.status_code == 404
    fhir = await db_client.get(
        f"/fhir/Device/{device_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fhir.status_code == 404
    missing_purpose = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
    )
    assert missing_purpose.status_code == 422
    invalid_purpose = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=clinician.headers(purpose="NOT_A_PURPOSE"),
    )
    assert invalid_purpose.status_code == 422
    unauthenticated = await db_client.get(f"/api/v1/clinical/medical-devices/{device_id}")
    assert unauthenticated.status_code == 401
    unauthenticated_post = await db_client.post(
        "/api/v1/clinical/medical-devices",
        json=_device(patient_id),
    )
    assert unauthenticated_post.status_code == 401
    unprovisioned = mint_token(sub="nobody-medical-device")
    denied_jwt = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
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
                    text("UPDATE medical_devices SET patient_identity_id = :pid WHERE id = :id"),
                    {"id": device_id, "pid": uuid4()},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE medical_devices SET code = 'changed' WHERE id = :id"),
                    {"id": device_id},
                )
        with pytest.raises(Exception, match="cannot be deleted|permission denied"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM medical_devices WHERE id = :id"),
                    {"id": device_id},
                )
        provenance = await connection.execute(
            text(
                """
                SELECT subject_type FROM clinical_provenances
                WHERE id = (SELECT provenance_id FROM medical_devices WHERE id = :id)
                """
            ),
            {"id": device_id},
        )
        assert provenance.scalar_one() == "MEDICAL_DEVICE"
        fk = await connection.execute(
            text(
                """
                SELECT delete_rule FROM information_schema.referential_constraints
                WHERE constraint_name = 'fk_medical_devices_provenance_id'
                """
            )
        )
        assert fk.scalar_one() == "RESTRICT"
        audit = await connection.execute(
            text("SELECT action, metadata::text FROM audit_events WHERE resource_id = :id"),
            {"id": device_id},
        )
        rows = list(audit)
        actions = {row[0] for row in rows}
        assert "MEDICAL_DEVICE_CREATED" in actions
        assert "MEDICAL_DEVICE_AMENDED" in actions
        assert "MEDICAL_DEVICE_ENTERED_IN_ERROR" in actions
        assert all("Cardiac pacemaker" not in (row[1] or "") for row in rows)
        assert all("Implanted 2019" not in (row[1] or "") for row in rows)
        assert all("14106009" not in (row[1] or "") for row in rows)
        later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'fhir_devices','fhir_medical_devices','care_plans','vital_signs'
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
                  AND table_name IN ('medical_devices','procedures','immunizations')
                """
            )
        )
        assert present.scalar_one() == 3


@requires_db
async def test_anonymous_merged_and_encounter_medical_device_binding(db_client, db_engine) -> None:
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
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(anonymous_id),
    )
    assert blocked.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE encounters SET encounter_class = 'AMB' WHERE id = :id"),
            {"id": emer.json()["id"]},
        )
    blocked_amb = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(anonymous_id, emer.json()["id"]),
    )
    assert blocked_amb.status_code == 409
    restored = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    allowed = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(anonymous_id, restored.json()["id"]),
    )
    assert allowed.status_code in {200, 201}

    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    foreign_patient = await _active_patient(db_client, other_registrar)
    mismatch = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(
            patient_id, (await _open_encounter(db_client, clinician, other_patient)).json()["id"]
        ),
    )
    assert mismatch.status_code == 409
    foreign = await _open_encounter(db_client, other, foreign_patient)
    cross_org = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(patient_id, foreign.json()["id"]),
    )
    assert cross_org.status_code == 404
    unknown_enc = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(patient_id, str(uuid4())),
    )
    assert unknown_enc.status_code == 404
    cross_identity = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(foreign_patient),
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
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(patient_id, cancelled.json()["id"]),
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
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(patient_id, erroneous.json()["id"]),
    )
    assert blocked_eie_enc.status_code == 409

    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Dev",
            "family_name": "Source",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B6"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Dev", family="Survivor", birth="1982-02-02"),
    )
    source_encounter = await _open_encounter(db_client, clinician, source.json()["id"])
    historical = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(source.json()["id"], source_encounter.json()["id"]),
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
            "reason": "Wave 2B.6 historical medical device",
            "evidence": merge_evidence("wave2b6-hist"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/medical-devices/{historical_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    rebound = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(source.json()["id"], source_encounter.json()["id"]),
    )
    assert rebound.status_code == 409
    created = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(source.json()["id"]),
    )
    assert created.json()["patient_identity_id"] == survivor.json()["id"]
    retired = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    rejected = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(retired),
    )
    assert rejected.status_code == 409
    missing = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(str(uuid4())),
    )
    assert missing.status_code == 404


@requires_db
async def test_medical_device_concurrency_facility_and_app_dml(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="treatment"),
        json=_device(patient_id, note="concurrent amend"),
    )
    device_id = created.json()["id"]

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/medical-devices/{device_id}/amend",
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
                WHERE resource_id = :id AND action = 'MEDICAL_DEVICE_AMENDED'
                """
            ),
            {"id": device_id},
        )
        assert events.scalar_one() == 1
        created_audit = await connection.execute(
            text(
                """
                SELECT metadata::text FROM audit_events
                WHERE resource_id = :id AND action = 'MEDICAL_DEVICE_CREATED'
                """
            ),
            {"id": device_id},
        )
        metadata = created_audit.scalar_one()
        assert "TREATMENT" in metadata

    other = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(patient_id, note="concurrent eie"),
    )
    other_id = other.json()["id"]

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/medical-devices/{other_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(void(), void())
    assert sorted([left.status_code, right.status_code]) == [200, 409]
    assert other.json()["version"] == 1
    async with db_engine.connect() as connection:
        eie_version = await connection.execute(
            text("SELECT version FROM medical_devices WHERE id = :id"),
            {"id": other_id},
        )
        assert eie_version.scalar_one() == 1

    race = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(patient_id, note="amend vs eie"),
    )
    race_id = race.json()["id"]

    async def amend_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/medical-devices/{race_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    async def void_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/medical-devices/{race_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    raced_left, raced_right = await asyncio.gather(amend_race(), void_race())
    codes = {raced_left.status_code, raced_right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status FROM medical_devices WHERE id = :id"),
            {"id": race_id},
        )
        assert row.scalar_one() == "ENTERED_IN_ERROR"
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'MEDICAL_DEVICE_ENTERED_IN_ERROR'
                """
            ),
            {"id": race_id},
        )
        amended_count = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'MEDICAL_DEVICE_AMENDED'
                """
            ),
            {"id": race_id},
        )
        assert eie.scalar_one() == 1
        assert amended_count.scalar_one() in {0, 1}

    in_scope = new_id()
    out_of_scope = new_id()
    async with db_engine.begin() as connection:
        for facility_id, code in ((in_scope, "DIN"), (out_of_scope, "DOUT")):
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
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=_headers(bound, "TREATMENT", str(in_scope)),
    )
    assert allowed.status_code == 200
    denied = await db_client.get(
        f"/api/v1/clinical/medical-devices/{device_id}",
        headers=_headers(bound, "TREATMENT", str(out_of_scope)),
    )
    assert denied.status_code == 403
    assert "Cardiac pacemaker" not in denied.text

    async with db_engine.connect() as connection:
        provenance = await connection.execute(
            text("SELECT provenance_id FROM medical_devices WHERE id = :id"),
            {"id": device_id},
        )
        provenance_id = provenance.scalar_one()
        checks = await connection.execute(
            text(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'medical_devices'::regclass
                  AND contype = 'c'
                """
            )
        )
        names = {row[0] for row in checks}
        assert any(name.endswith("medical_device_category") for name in names)
        assert any(name.endswith("medical_device_association_status") for name in names)
        assert any(name.endswith("medical_device_status") for name in names)
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="foreign key|fk_medical_devices_provenance"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO medical_devices (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, association_status, status,
                            recorded_at, version, provenance_id
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               category, code_system, code, association_status, 'ACTIVE',
                               now(), 1, :bad
                        FROM medical_devices WHERE id = :id
                        """
                    ),
                    {"id": device_id, "bad": uuid4()},
                )
        with pytest.raises(Exception, match=PROVENANCE_DELETE_DENIED):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM clinical_provenances WHERE id = :id"),
                    {"id": provenance_id},
                )
        with pytest.raises(Exception, match="invalid medical device status transition"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE medical_devices SET status = 'ACTIVE' WHERE id = :id"),
                    {"id": device_id},
                )
        with pytest.raises(Exception, match="medical_device_category|violates check"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO medical_devices (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, association_status, status,
                            recorded_at, version
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               'IMPLANTED', code_system, code, association_status, 'ACTIVE',
                               now(), 1
                        FROM medical_devices WHERE id = :id
                        """
                    ),
                    {"id": device_id},
                )

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM medical_devices WHERE id = :id"),
                        {"id": device_id},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            "UPDATE medical_devices SET code_display = 'Insulin pump' "
                            "WHERE id = :id"
                        ),
                        {"id": device_id},
                    )
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE medical_devices"))
    finally:
        await engine.dispose()
