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


def _procedure(
    patient_id: str,
    encounter_id: str | None = None,
    *,
    note: str | None = "Uneventful recovery",
    category: str = "PERFORMED",
    occurrence_at: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "patient_identity_id": patient_id,
        "category": category,
        "code": {"system": SNOMED, "code": "80146002", "display": "Appendectomy"},
    }
    if note is not None:
        payload["note_text"] = note
    if occurrence_at is not None:
        payload["occurrence_at"] = occurrence_at
    if encounter_id is not None:
        payload["encounter_id"] = encounter_id
    return payload


def _amend_body(
    *,
    note: str | None = "Corrected note",
    occurrence_at: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"note_text": note}
    if occurrence_at is not None:
        payload["occurrence_at"] = occurrence_at
    return payload


@requires_db
async def test_procedure_lifecycle_identity_and_authorization(db_client, db_engine) -> None:
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
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_procedure(patient_id), "category": "NOT_A_CATEGORY"},
    )
    assert invalid.status_code == 422
    invalid_code = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_procedure(patient_id), "code": {"system": "", "code": "80146002"}},
    )
    assert invalid_code.status_code == 422

    created = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id, encounter_id),
    )
    assert created.status_code in {200, 201}
    body = created.json()
    assert body["status"] == "ACTIVE"
    assert body["version"] == 1
    assert body["category"] == "PERFORMED"
    procedure_id = body["id"]

    denied = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_procedure(patient_id),
    )
    assert denied.status_code == 403
    assert "Appendectomy" not in denied.text
    assert "Uneventful recovery" not in denied.text
    officer_denied = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=officer.headers(purpose="TREATMENT"),
        json=_procedure(patient_id),
    )
    assert officer_denied.status_code == 403
    registrar_read = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=registrar.headers(purpose="TREATMENT"),
    )
    assert registrar_read.status_code == 403
    officer_read = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=officer.headers(purpose="TREATMENT"),
    )
    assert officer_read.status_code == 403

    listed = await db_client.get(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert listed.status_code == 200
    assert procedure_id in {item["id"] for item in listed.json()}

    auditor_read = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=auditor.headers(purpose="AUDIT"),
    )
    assert auditor_read.status_code == 200
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
    platform_read = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=platform.headers(purpose="TREATMENT"),
    )
    assert platform_read.status_code == 200

    amended = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(),
    )
    assert amended.status_code == 200
    assert amended.json()["status"] == "AMENDED"
    assert amended.json()["note_text"] == "Corrected note"
    assert amended.json()["version"] == 2
    noop = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(),
    )
    assert noop.status_code == 409

    voided = await db_client.post(
        f"/api/v1/clinical/procedures/{procedure_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    assert voided.json()["version"] == 2
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

    cross = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "sqlalchemy" not in cross.text.lower()
    assert "80146002" not in cross.text
    assert "Appendectomy" not in cross.text
    unknown = await db_client.get(
        f"/api/v1/clinical/procedures/{uuid4()}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unknown.status_code == 404
    deleted = await db_client.delete(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
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
    unauthenticated = await db_client.get(f"/api/v1/clinical/procedures/{procedure_id}")
    assert unauthenticated.status_code == 401
    unauthenticated_post = await db_client.post(
        "/api/v1/clinical/procedures",
        json=_procedure(patient_id),
    )
    assert unauthenticated_post.status_code == 401
    unprovisioned = mint_token(sub="nobody-procedure")
    denied_jwt = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
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
                    text("UPDATE procedures SET patient_identity_id = :pid WHERE id = :id"),
                    {"id": procedure_id, "pid": uuid4()},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE procedures SET code = 'changed' WHERE id = :id"),
                    {"id": procedure_id},
                )
        with pytest.raises(Exception, match="cannot be deleted"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM procedures WHERE id = :id"),
                    {"id": procedure_id},
                )
        provenance = await connection.execute(
            text(
                """
                SELECT subject_type FROM clinical_provenances
                WHERE id = (SELECT provenance_id FROM procedures WHERE id = :id)
                """
            ),
            {"id": procedure_id},
        )
        assert provenance.scalar_one() == "PROCEDURE"
        fk = await connection.execute(
            text(
                """
                SELECT delete_rule FROM information_schema.referential_constraints
                WHERE constraint_name = 'fk_procedures_provenance_id'
                """
            )
        )
        assert fk.scalar_one() == "RESTRICT"
        audit = await connection.execute(
            text("SELECT action, metadata::text FROM audit_events WHERE resource_id = :id"),
            {"id": procedure_id},
        )
        rows = list(audit)
        actions = {row[0] for row in rows}
        assert "PROCEDURE_CREATED" in actions
        assert "PROCEDURE_AMENDED" in actions
        assert "PROCEDURE_ENTERED_IN_ERROR" in actions
        assert all("Appendectomy" not in (row[1] or "") for row in rows)
        assert all("Uneventful recovery" not in (row[1] or "") for row in rows)
        assert all("80146002" not in (row[1] or "") for row in rows)
        later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'fhir_procedures','care_plans','treatments'
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
                  AND table_name IN ('procedures','immunizations','consents')
                """
            )
        )
        assert present.scalar_one() == 3


@requires_db
async def test_anonymous_merged_and_encounter_procedure_binding(db_client, db_engine) -> None:
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
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(anonymous_id),
    )
    assert blocked.status_code == 409
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

    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    foreign_patient = await _active_patient(db_client, other_registrar)
    mismatch = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(
            patient_id, (await _open_encounter(db_client, clinician, other_patient)).json()["id"]
        ),
    )
    assert mismatch.status_code == 409
    foreign = await _open_encounter(db_client, other, foreign_patient)
    cross_org = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id, foreign.json()["id"]),
    )
    assert cross_org.status_code == 404
    unknown_enc = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id, str(uuid4())),
    )
    assert unknown_enc.status_code == 404
    cross_identity = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(foreign_patient),
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

    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Prc",
            "family_name": "Source",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B5"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Prc", family="Survivor", birth="1982-02-02"),
    )
    source_encounter = await _open_encounter(db_client, clinician, source.json()["id"])
    historical = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(source.json()["id"], source_encounter.json()["id"]),
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
            "reason": "Wave 2B.5 historical procedure",
            "evidence": merge_evidence("wave2b5-hist"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/procedures/{historical_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    rebound = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(source.json()["id"], source_encounter.json()["id"]),
    )
    assert rebound.status_code == 409
    created = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(source.json()["id"]),
    )
    assert created.json()["patient_identity_id"] == survivor.json()["id"]
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
async def test_procedure_concurrency_facility_and_app_dml(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="treatment"),
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
        events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'PROCEDURE_AMENDED'
                """
            ),
            {"id": procedure_id},
        )
        assert events.scalar_one() == 1
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
    assert other.json()["version"] == 1
    async with db_engine.connect() as connection:
        eie_version = await connection.execute(
            text("SELECT version FROM procedures WHERE id = :id"),
            {"id": other_id},
        )
        assert eie_version.scalar_one() == 1

    race = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id, note="amend vs eie"),
    )
    race_id = race.json()["id"]

    async def amend_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/procedures/{race_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    async def void_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/procedures/{race_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    raced_left, raced_right = await asyncio.gather(amend_race(), void_race())
    codes = {raced_left.status_code, raced_right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status FROM procedures WHERE id = :id"),
            {"id": race_id},
        )
        assert row.scalar_one() == "ENTERED_IN_ERROR"
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'PROCEDURE_ENTERED_IN_ERROR'
                """
            ),
            {"id": race_id},
        )
        amended_count = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'PROCEDURE_AMENDED'
                """
            ),
            {"id": race_id},
        )
        assert eie.scalar_one() == 1
        assert amended_count.scalar_one() in {0, 1}

    in_scope = new_id()
    out_of_scope = new_id()
    async with db_engine.begin() as connection:
        for facility_id, code in ((in_scope, "PIN"), (out_of_scope, "POUT")):
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
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=_headers(bound, "TREATMENT", str(in_scope)),
    )
    assert allowed.status_code == 200
    denied = await db_client.get(
        f"/api/v1/clinical/procedures/{procedure_id}",
        headers=_headers(bound, "TREATMENT", str(out_of_scope)),
    )
    assert denied.status_code == 403
    assert "Appendectomy" not in denied.text

    async with db_engine.connect() as connection:
        provenance = await connection.execute(
            text("SELECT provenance_id FROM procedures WHERE id = :id"),
            {"id": procedure_id},
        )
        provenance_id = provenance.scalar_one()
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="foreign key|fk_procedures_provenance"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO procedures (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, status, recorded_at, version, provenance_id
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               category, code_system, code, 'ACTIVE', now(), 1, :bad
                        FROM procedures WHERE id = :id
                        """
                    ),
                    {"id": procedure_id, "bad": uuid4()},
                )
        with pytest.raises(Exception, match="insert-only|foreign key|fk_procedures_provenance"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM clinical_provenances WHERE id = :id"),
                    {"id": provenance_id},
                )
        with pytest.raises(Exception, match="invalid procedure status transition"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE procedures SET status = 'ACTIVE' WHERE id = :id"),
                    {"id": procedure_id},
                )

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM procedures WHERE id = :id"),
                        {"id": procedure_id},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE procedures SET code_display = 'Bypass' WHERE id = :id"),
                        {"id": procedure_id},
                    )
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE procedures"))
    finally:
        await engine.dispose()
