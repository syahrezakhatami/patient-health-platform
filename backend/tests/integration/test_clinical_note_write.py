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
from tests.integration.clinical_notes import (
    create_note_body,
    finalize_note_body,
    new_idempotency_key,
    note_write_headers,
    restore_note_write_idempotency_app_dml_privileges,
    update_note_body,
)
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter

pytestmark = [pytest.mark.integration]

APP_DML_URL = os.environ.get(
    "APP_DML_DATABASE_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


async def _create_note(
    db_client,
    actor,
    patient_id,
    encounter_id,
    *,
    body="Clinical assessment.",
    key=None,
    facility_id=None,
    note_type="PROGRESS",
):
    return await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(
            actor,
            idempotency_key=key or new_idempotency_key("create"),
            facility_id=facility_id,
        ),
        json=create_note_body(patient_id, encounter_id, note_type=note_type, body_text=body),
    )


async def _seed_facility(db_engine, organization_id, code: str):
    facility_id = new_id()
    async with db_engine.begin() as connection:
        await connection.execute(
            FacilityModel.__table__.insert().values(
                id=facility_id,
                organization_id=organization_id,
                name=code,
                code=code,
                facility_type=FacilityType.HOSPITAL_SITE,
                status=FacilityStatus.ACTIVE,
            )
        )
    return facility_id


async def _seed_facility_clinician(db_engine, organization_id, facility_id) -> SeededActor:
    bound_user = new_id()
    subject = f"user-{bound_user}"
    async with db_engine.begin() as connection:
        role_id = (
            await connection.execute(
                select(RoleModel.id).where(RoleModel.code == RoleCode.CLINICIAN)
            )
        ).scalar_one()
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
                organization_id=organization_id,
                facility_id=facility_id,
                role_id=role_id,
                status=MembershipStatus.ACTIVE,
            )
        )
    return SeededActor(bound_user, subject, organization_id, mint_token(sub=subject))


@requires_db
async def test_clinical_note_write_create_matrix_and_privacy(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]

    missing_key = await db_client.post(
        "/api/v1/clinical/notes",
        headers=clinician.headers(purpose="TREATMENT"),
        json=create_note_body(patient_id, encounter_id),
    )
    assert missing_key.status_code == 422
    assert missing_key.json()["error"]["code"] == "idempotency_key_required"

    bad_key = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(clinician, idempotency_key="bad key!"),
        json=create_note_body(patient_id, encounter_id),
    )
    assert bad_key.status_code == 422
    assert bad_key.json()["error"]["code"] == "invalid_idempotency_key"

    missing_purpose = await db_client.post(
        "/api/v1/clinical/notes",
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
            "Idempotency-Key": new_idempotency_key(),
        },
        json=create_note_body(patient_id, encounter_id),
    )
    assert missing_purpose.status_code == 422

    patient_aud = mint_token(sub=clinician.subject, aud="php-patient")
    wrong_audience = await db_client.post(
        "/api/v1/clinical/notes",
        headers={
            "Authorization": f"Bearer {patient_aud}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
            "Idempotency-Key": new_idempotency_key(),
        },
        json=create_note_body(patient_id, encounter_id),
    )
    assert wrong_audience.status_code == 401

    empty = await _create_note(db_client, clinician, patient_id, encounter_id, body="   ")
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "note_body_required"

    too_long = await _create_note(db_client, clinician, patient_id, encounter_id, body="x" * 20001)
    assert too_long.status_code == 422
    assert "xxxxx" not in too_long.text

    secret = "UNIQUE_NOTE_BODY_SHOULD_NOT_ECHO"
    malformed = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(clinician, idempotency_key=new_idempotency_key()),
        json={
            "expected_patient_identity_id": "not-a-uuid",
            "encounter_id": encounter_id,
            "note_type": "PROGRESS",
            "body_text": secret,
        },
    )
    assert malformed.status_code == 422
    assert secret not in malformed.text
    assert "input" not in malformed.text

    authority = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(clinician, idempotency_key=new_idempotency_key()),
        json={
            **create_note_body(patient_id, encounter_id),
            "author_id": str(uuid4()),
            "organization_id": str(clinician.organization_id),
        },
    )
    assert authority.status_code == 422

    unicode_body = "Nyeri dada. Assessment complete. 胸痛评估。"
    created = await _create_note(db_client, clinician, patient_id, encounter_id, body=unicode_body)
    assert created.status_code in {200, 201}
    assert created.json()["body_text"] == unicode_body
    assert created.json()["version"] == 1
    assert created.json()["record_status"] == "DRAFT"
    assert created.json()["patient_identity_id"] == patient_id
    async with db_engine.connect() as connection:
        author = await connection.execute(
            text("SELECT author_id FROM clinical_notes WHERE id = :id"),
            {"id": created.json()["id"]},
        )
        assert str(author.scalar_one()) == str(clinician.user_id)

    async with db_engine.connect() as connection:
        audit = await connection.execute(
            text(
                """
                SELECT action, metadata::text FROM audit_events
                WHERE resource_id = :id AND action = 'CLINICAL_NOTE_CREATED'
                """
            ),
            {"id": created.json()["id"]},
        )
        row = audit.one()
        assert row[0] == "CLINICAL_NOTE_CREATED"
        assert unicode_body not in (row[1] or "")
        assert "body_text" not in (row[1] or "")
        provenance = await connection.execute(
            text(
                """
                SELECT count(*) FROM clinical_provenances
                WHERE subject_type = 'CLINICAL_NOTE' AND subject_id = :id
                """
            ),
            {"id": created.json()["id"]},
        )
        assert provenance.scalar_one() == 1


@requires_db
async def test_clinical_note_wrong_patient_and_cross_org_concealed(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    other_registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=other.organization_id
    )
    patient_one = await _active_patient(db_client, registrar)
    patient_two = await _active_patient(db_client, registrar)
    encounter_two = (await _open_encounter(db_client, clinician, patient_two)).json()["id"]
    foreign_patient = await _active_patient(db_client, other_registrar)
    foreign_encounter = (await _open_encounter(db_client, other, foreign_patient)).json()["id"]

    async with db_engine.connect() as connection:
        before = (
            await connection.execute(text("SELECT count(*) FROM clinical_notes"))
        ).scalar_one()

    wrong_patient = await _create_note(db_client, clinician, patient_one, encounter_two)
    assert wrong_patient.status_code == 404
    assert wrong_patient.json()["error"]["code"] == "not_found"
    assert "Encounter not found" in wrong_patient.json()["error"]["message"]

    cross_org = await _create_note(db_client, clinician, patient_one, foreign_encounter)
    assert cross_org.status_code == 404
    assert str(other.organization_id) not in cross_org.text
    assert str(foreign_patient) not in cross_org.text

    async with db_engine.connect() as connection:
        after = (await connection.execute(text("SELECT count(*) FROM clinical_notes"))).scalar_one()
    assert after == before


@requires_db
async def test_clinical_note_merged_historical_encounter_and_retired(db_client, db_engine) -> None:
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
            "given_name": "Merge",
            "family_name": "Source",
            "birth_date": "1977-07-07",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("NOTE"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Merge", family="Survivor", birth="1977-07-07"),
    )
    source_id = source.json()["id"]
    survivor_id = survivor.json()["id"]
    historical = await _open_encounter(db_client, clinician, source_id)
    assert historical.status_code in {200, 201}
    assert historical.json()["patient_identity_id"] == source_id
    encounter_id = historical.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source_id,
            "target_identity_id": survivor_id,
            "reason": "Clinical note historical encounter",
            "evidence": merge_evidence("note-merge"),
        },
    )
    assert merged.status_code in {200, 201}

    created = await _create_note(db_client, clinician, survivor_id, encounter_id)
    assert created.status_code in {200, 201}
    assert created.json()["patient_identity_id"] == source_id
    note_id = created.json()["id"]

    updated = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json=update_note_body(survivor_id, 1, "Updated after merge."),
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["patient_identity_id"] == source_id

    finalized = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}/finalize",
        headers=note_write_headers(clinician, idempotency_key=new_idempotency_key("merge-fin")),
        json=finalize_note_body(survivor_id),
    )
    assert finalized.status_code == 200
    assert finalized.json()["record_status"] == "FINAL"
    assert finalized.json()["version"] == 2
    assert finalized.json()["patient_identity_id"] == source_id

    retired = await _active_patient(db_client, registrar)
    retired_encounter = (await _open_encounter(db_client, clinician, retired)).json()["id"]
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    rejected = await _create_note(db_client, clinician, retired, retired_encounter)
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "identity_not_usable"


@requires_db
async def test_clinical_note_facility_matrix_and_header_absent_scope(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    facility_a = await _seed_facility(db_engine, clinician.organization_id, "NTA")
    facility_b = await _seed_facility(db_engine, clinician.organization_id, "NTB")
    bound_a = await _seed_facility_clinician(db_engine, clinician.organization_id, facility_a)
    bound_b = await _seed_facility_clinician(db_engine, clinician.organization_id, facility_b)
    patient_id = await _active_patient(db_client, registrar)

    encounter_a = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=note_write_headers(clinician, facility_id=facility_a, purpose="TREATMENT"),
        json={"patient_identity_id": patient_id, "encounter_class": "AMB"},
    )
    assert encounter_a.status_code in {200, 201}
    encounter_a_id = encounter_a.json()["id"]
    assert encounter_a.json()["facility_id"] == str(facility_a)

    match = await _create_note(
        db_client, clinician, patient_id, encounter_a_id, facility_id=facility_a
    )
    assert match.status_code in {200, 201}
    assert match.json()["facility_id"] == str(facility_a)

    mismatch = await _create_note(
        db_client, clinician, patient_id, encounter_a_id, facility_id=facility_b
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "encounter_facility_mismatch"

    inherit = await _create_note(db_client, clinician, patient_id, encounter_a_id)
    assert inherit.status_code in {200, 201}
    assert inherit.json()["facility_id"] == str(facility_a)

    scoped_ok = await _create_note(db_client, bound_a, patient_id, encounter_a_id)
    assert scoped_ok.status_code in {200, 201}
    scoped_denied = await _create_note(db_client, bound_b, patient_id, encounter_a_id)
    assert scoped_denied.status_code == 403

    null_encounter = await _open_encounter(db_client, clinician, patient_id)
    null_id = null_encounter.json()["id"]
    assert null_encounter.json()["facility_id"] is None
    attributed = await _create_note(
        db_client, clinician, patient_id, null_id, facility_id=facility_a
    )
    assert attributed.status_code in {200, 201}
    assert attributed.json()["facility_id"] == str(facility_a)
    org_only = await _create_note(db_client, clinician, patient_id, null_id)
    assert org_only.status_code in {200, 201}
    assert org_only.json()["facility_id"] is None

    update_mismatch = await db_client.post(
        f"/api/v1/clinical/notes/{match.json()['id']}",
        headers=note_write_headers(clinician, facility_id=facility_b, purpose="TREATMENT"),
        json=update_note_body(patient_id, 1, "should not write"),
    )
    assert update_mismatch.status_code == 409
    assert update_mismatch.json()["error"]["code"] == "note_facility_mismatch"


@requires_db
async def test_clinical_note_idempotency_replay_conflict_and_concurrency(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    other = await seed_actor(
        db_engine, role_code=RoleCode.CLINICIAN, organization_id=clinician.organization_id
    )
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter = (await _open_encounter(db_client, clinician, patient_id)).json()
    encounter_id = encounter["id"]
    other_encounter = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    key = new_idempotency_key("same")
    body = "Idempotent create body"

    first = await _create_note(db_client, clinician, patient_id, encounter_id, body=body, key=key)
    assert first.status_code in {200, 201}
    note_id = first.json()["id"]

    replay = await _create_note(db_client, clinician, patient_id, encounter_id, body=body, key=key)
    assert replay.status_code == 200
    assert replay.json()["id"] == note_id

    different_body = await _create_note(
        db_client, clinician, patient_id, encounter_id, body="Different body", key=key
    )
    assert different_body.status_code == 409
    assert different_body.json()["error"]["code"] == "idempotency_key_conflict"
    assert "Different body" not in different_body.text

    different_encounter = await _create_note(
        db_client, clinician, patient_id, other_encounter, body=body, key=key
    )
    assert different_encounter.status_code == 409

    different_type = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(clinician, idempotency_key=key),
        json=create_note_body(patient_id, encounter_id, note_type="ED", body_text=body),
    )
    assert different_type.status_code == 409

    other_actor = await _create_note(db_client, other, patient_id, encounter_id, body=body, key=key)
    assert other_actor.status_code in {200, 201}
    assert other_actor.json()["id"] != note_id

    other_org = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    other_org_note = await _create_note(
        db_client, other_org, patient_id, encounter_id, body=body, key=key
    )
    assert other_org_note.status_code == 404

    concurrent_key = new_idempotency_key("concurrent")

    async def create_same() -> object:
        return await _create_note(
            db_client,
            clinician,
            patient_id,
            encounter_id,
            body="Concurrent same key",
            key=concurrent_key,
        )

    left, right = await asyncio.gather(create_same(), create_same())
    statuses = sorted([left.status_code, right.status_code])
    assert statuses[0] in {200, 201}
    assert statuses[1] in {200, 201}
    assert left.json()["id"] == right.json()["id"]
    concurrent_id = left.json()["id"]
    async with db_engine.connect() as connection:
        notes = await connection.execute(
            text("SELECT count(*) FROM clinical_notes WHERE id = :id"),
            {"id": concurrent_id},
        )
        assert notes.scalar_one() == 1
        created = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CLINICAL_NOTE_CREATED'
                """
            ),
            {"id": concurrent_id},
        )
        assert created.scalar_one() == 1
        provenances = await connection.execute(
            text(
                """
                SELECT count(*) FROM clinical_provenances
                WHERE subject_type = 'CLINICAL_NOTE' AND subject_id = :id
                """
            ),
            {"id": concurrent_id},
        )
        assert provenances.scalar_one() == 1
        mappings = await connection.execute(
            text(
                """
                SELECT count(*) FROM clinical_note_write_idempotency
                WHERE organization_id = :org AND actor_id = :actor
                  AND operation = 'NOTE_CREATE' AND idempotency_key = :key
                """
            ),
            {
                "org": clinician.organization_id,
                "actor": clinician.user_id,
                "key": concurrent_key,
            },
        )
        assert mappings.scalar_one() == 1

    async with db_engine.connect() as connection:
        first_audits = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CLINICAL_NOTE_CREATED'
                """
            ),
            {"id": note_id},
        )
        assert first_audits.scalar_one() == 1


@requires_db
async def test_clinical_note_update_version_finalize_and_races(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    other = await seed_actor(
        db_engine, role_code=RoleCode.CLINICIAN, organization_id=clinician.organization_id
    )
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    created = await _create_note(db_client, clinician, patient_id, encounter_id, body="Draft one")
    note_id = created.json()["id"]
    assert created.json()["version"] == 1

    stale = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json=update_note_body(patient_id, 99, "stale overwrite"),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "note_version_conflict"
    assert "stale overwrite" not in stale.text

    wrong_patient = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json=update_note_body(other_patient, 1, "wrong patient"),
    )
    assert wrong_patient.status_code == 404

    updated = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json=update_note_body(patient_id, 1, "Draft two"),
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["body_text"] == "Draft two"

    cancelled = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"patient_identity_id": patient_id, "encounter_class": "AMB"},
    )
    cancelled_id = cancelled.json()["id"]
    await db_client.post(
        f"/api/v1/clinical/encounters/{cancelled_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "CANCELLED"},
    )
    blocked_cancelled = await _create_note(db_client, clinician, patient_id, cancelled_id)
    assert blocked_cancelled.status_code == 409
    assert blocked_cancelled.json()["error"]["code"] == "encounter_not_documentable"

    finishable = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"patient_identity_id": patient_id, "encounter_class": "AMB"},
    )
    finish_id = finishable.json()["id"]
    await db_client.post(
        f"/api/v1/clinical/encounters/{finish_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "IN_PROGRESS"},
    )
    await db_client.post(
        f"/api/v1/clinical/encounters/{finish_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "FINISHED"},
    )
    finished_note = await _create_note(db_client, clinician, patient_id, finish_id)
    assert finished_note.status_code in {200, 201}

    race_note = await _create_note(db_client, clinician, patient_id, encounter_id, body="Race body")
    race_id = race_note.json()["id"]

    async def update_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/notes/{race_id}",
            headers=clinician.headers(purpose="TREATMENT"),
            json=update_note_body(patient_id, 1, "Updated before sign"),
        )

    async def finalize_race(key: str) -> object:
        return await db_client.post(
            f"/api/v1/clinical/notes/{race_id}/finalize",
            headers=note_write_headers(clinician, idempotency_key=key),
            json=finalize_note_body(patient_id),
        )

    upd, fin = await asyncio.gather(update_race(), finalize_race(new_idempotency_key("sign-a")))
    codes = {upd.status_code, fin.status_code}
    assert 200 in codes
    async with db_engine.connect() as connection:
        status = await connection.execute(
            text("SELECT record_status, version, body_text FROM clinical_notes WHERE id = :id"),
            {"id": race_id},
        )
        record_status, version, body_text = status.one()
    if fin.status_code == 200 and upd.status_code == 409:
        assert record_status == "FINAL"
        assert upd.json()["error"]["code"] == "note_not_draft"
        assert body_text == "Race body"
    elif upd.status_code == 200 and fin.status_code == 200:
        assert record_status == "FINAL"
        assert version == 2
        assert body_text == "Updated before sign"
    else:
        raise AssertionError((upd.status_code, fin.status_code))

    later_update = await db_client.post(
        f"/api/v1/clinical/notes/{race_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json=update_note_body(patient_id, version, "after final"),
    )
    assert later_update.status_code == 409
    assert later_update.json()["error"]["code"] == "note_not_draft"

    sign_note = await _create_note(db_client, clinician, patient_id, encounter_id, body="To sign")
    sign_id = sign_note.json()["id"]
    finalize_key = new_idempotency_key("finalize-same")
    first_final = await db_client.post(
        f"/api/v1/clinical/notes/{sign_id}/finalize",
        headers=note_write_headers(clinician, idempotency_key=finalize_key),
        json=finalize_note_body(patient_id),
    )
    assert first_final.status_code == 200
    replay_final = await db_client.post(
        f"/api/v1/clinical/notes/{sign_id}/finalize",
        headers=note_write_headers(clinician, idempotency_key=finalize_key),
        json=finalize_note_body(patient_id),
    )
    assert replay_final.status_code == 200
    second_key = await db_client.post(
        f"/api/v1/clinical/notes/{sign_id}/finalize",
        headers=note_write_headers(
            clinician, idempotency_key=new_idempotency_key("finalize-other")
        ),
        json=finalize_note_body(patient_id),
    )
    assert second_key.status_code == 409
    assert second_key.json()["error"]["code"] == "note_not_draft"

    other_note = await _create_note(
        db_client, clinician, patient_id, encounter_id, body="Other note"
    )
    reused = await db_client.post(
        f"/api/v1/clinical/notes/{other_note.json()['id']}/finalize",
        headers=note_write_headers(clinician, idempotency_key=finalize_key),
        json=finalize_note_body(patient_id),
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "idempotency_key_conflict"

    async with db_engine.connect() as connection:
        finals = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CLINICAL_NOTE_FINALIZED'
                """
            ),
            {"id": sign_id},
        )
        assert finals.scalar_one() == 1
        version_row = await connection.execute(
            text("SELECT version FROM clinical_notes WHERE id = :id"),
            {"id": sign_id},
        )
        assert version_row.scalar_one() == 1

    cross_author = await _create_note(
        db_client, clinician, patient_id, encounter_id, body="Cross author"
    )
    cross = await db_client.post(
        f"/api/v1/clinical/notes/{cross_author.json()['id']}/finalize",
        headers=note_write_headers(other, idempotency_key=new_idempotency_key("cross")),
        json=finalize_note_body(patient_id),
    )
    assert cross.status_code == 200
    async with db_engine.connect() as connection:
        author = await connection.execute(
            text("SELECT author_id FROM clinical_notes WHERE id = :id"),
            {"id": cross_author.json()["id"]},
        )
        assert str(author.scalar_one()) == str(clinician.user_id)

    async def double_finalize() -> tuple[object, object]:
        draft = await _create_note(db_client, clinician, patient_id, encounter_id, body="Double")
        note = draft.json()["id"]

        async def one(key: str) -> object:
            return await db_client.post(
                f"/api/v1/clinical/notes/{note}/finalize",
                headers=note_write_headers(clinician, idempotency_key=key),
                json=finalize_note_body(patient_id),
            )

        return await asyncio.gather(one(new_idempotency_key("d1")), one(new_idempotency_key("d2")))

    d1, d2 = await double_finalize()
    assert sorted([d1.status_code, d2.status_code]) == [200, 409]


@requires_db
async def test_clinical_note_db_immutability_privileges_and_migration(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    created = await _create_note(
        db_client, clinician, patient_id, encounter_id, body="Immutable draft"
    )
    note_id = created.json()["id"]
    await restore_note_write_idempotency_app_dml_privileges(db_engine)

    async with db_engine.connect() as connection:
        version = await connection.execute(text("SELECT version_num FROM alembic_version"))
        assert version.scalar_one() == "20260814_0020"
        heads = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'clinical_note_write_idempotency'
                """
            )
        )
        assert heads.scalar_one() == 1
        constraint = await connection.execute(
            text(
                """
                SELECT count(*) FROM pg_constraint
                WHERE conname = 'uq_clinical_note_write_idempotency_scope'
                """
            )
        )
        assert constraint.scalar_one() == 1
        trigger = await connection.execute(
            text(
                """
                SELECT count(*) FROM pg_trigger
                WHERE tgname = 'trg_clinical_note_write_idempotency_immutable'
                """
            )
        )
        assert trigger.scalar_one() == 1
        privileges = await connection.execute(
            text(
                """
                SELECT privilege_type FROM information_schema.role_table_grants
                WHERE grantee = 'app_dml' AND table_name = 'clinical_note_write_idempotency'
                """
            )
        )
        granted = {row[0] for row in privileges}

    async def assert_immutable(sql: str, params: dict, *, pattern: str = "immutable") -> None:
        async with db_engine.connect() as connection:
            with pytest.raises(Exception, match=pattern):
                async with connection.begin():
                    await connection.execute(text(sql), params)

    await assert_immutable(
        "UPDATE clinical_notes SET organization_id = :org WHERE id = :id",
        {"id": note_id, "org": uuid4()},
    )
    await assert_immutable(
        "UPDATE clinical_notes SET facility_id = :fid WHERE id = :id",
        {"id": note_id, "fid": uuid4()},
    )
    await assert_immutable(
        "UPDATE clinical_notes SET author_id = :aid WHERE id = :id",
        {"id": note_id, "aid": uuid4()},
    )
    await assert_immutable(
        "UPDATE clinical_notes SET note_type = 'ED' WHERE id = :id",
        {"id": note_id},
    )
    await assert_immutable(
        "UPDATE clinical_notes SET patient_identity_id = :pid WHERE id = :id",
        {"id": note_id, "pid": uuid4()},
    )
    await assert_immutable(
        "UPDATE clinical_notes SET encounter_id = :eid WHERE id = :id",
        {"id": note_id, "eid": uuid4()},
    )
    await assert_immutable(
        """
        UPDATE clinical_note_write_idempotency
        SET request_fingerprint = repeat('a', 64)
        WHERE note_id = :id
        """,
        {"id": note_id},
        pattern="immutable|permission denied",
    )

    if granted:
        assert {"SELECT", "INSERT"} <= granted
        assert "UPDATE" not in granted
        assert "DELETE" not in granted
        assert "TRUNCATE" not in granted

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            selected = await connection.execute(
                text("SELECT id FROM clinical_note_write_idempotency WHERE note_id = :id"),
                {"id": note_id},
            )
            assert selected.scalar_one_or_none() is not None
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="immutable|permission denied"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            """
                            UPDATE clinical_note_write_idempotency
                            SET request_fingerprint = repeat('b', 64)
                            WHERE note_id = :id
                            """
                        ),
                        {"id": note_id},
                    )
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="immutable|permission denied"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM clinical_note_write_idempotency WHERE note_id = :id"),
                        {"id": note_id},
                    )
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE clinical_note_write_idempotency"))
    finally:
        await engine.dispose()
