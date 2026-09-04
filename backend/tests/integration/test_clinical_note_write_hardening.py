import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.iam.infrastructure.models import RoleModel
from sqlalchemy import select, text
from tests.integration.clinical_notes import (
    create_note_body,
    finalize_note_body,
    new_idempotency_key,
    note_write_headers,
    restore_note_write_idempotency_app_dml_privileges,
    update_note_body,
)
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_clinical_note_write import (
    _create_note,
    _seed_facility,
    _seed_facility_clinician,
)
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter

pytestmark = [pytest.mark.integration]

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@requires_db
async def test_create_and_finalize_replay_reject_wrong_patient_context(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_a = await _active_patient(db_client, registrar)
    patient_b = await _active_patient(db_client, registrar)
    encounter_a = (await _open_encounter(db_client, clinician, patient_a)).json()["id"]
    create_key = new_idempotency_key("wrong-create")
    created = await _create_note(
        db_client, clinician, patient_a, encounter_a, body="Patient A assessment.", key=create_key
    )
    assert created.status_code in {200, 201}
    note_id = created.json()["id"]
    async with db_engine.connect() as connection:
        before = (
            await connection.execute(text("SELECT count(*) FROM clinical_notes"))
        ).scalar_one()

    replay_wrong = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(clinician, idempotency_key=create_key),
        json=create_note_body(patient_b, encounter_a, body_text="Patient A assessment."),
    )
    assert replay_wrong.status_code == 404
    assert replay_wrong.json()["error"]["code"] == "not_found"
    assert note_id not in replay_wrong.text
    assert "Patient A assessment." not in replay_wrong.text

    finalize_key = new_idempotency_key("wrong-final")
    finalized = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}/finalize",
        headers=note_write_headers(clinician, idempotency_key=finalize_key),
        json=finalize_note_body(patient_a),
    )
    assert finalized.status_code == 200
    wrong_finalize = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}/finalize",
        headers=note_write_headers(clinician, idempotency_key=finalize_key),
        json=finalize_note_body(patient_b),
    )
    assert wrong_finalize.status_code == 404
    assert wrong_finalize.json()["error"]["code"] == "not_found"
    assert wrong_finalize.json().get("record_status") is None
    assert "Patient A assessment." not in wrong_finalize.text
    async with db_engine.connect() as connection:
        after = (await connection.execute(text("SELECT count(*) FROM clinical_notes"))).scalar_one()
        status = await connection.execute(
            text("SELECT record_status FROM clinical_notes WHERE id = :id"),
            {"id": note_id},
        )
        assert status.scalar_one() == "FINAL"
    assert after == before


@requires_db
async def test_same_person_expected_patient_difference_conflicts_after_safety(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
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
                    "identifier_value": unique_mrn("FP"),
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
    encounter_id = (await _open_encounter(db_client, clinician, source_id)).json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source_id,
            "target_identity_id": survivor_id,
            "reason": "Fingerprint expected-patient difference",
            "evidence": merge_evidence("fp-merge"),
        },
    )
    assert merged.status_code in {200, 201}
    key = new_idempotency_key("same-person")
    body = "Same-person fingerprint body"
    created = await _create_note(
        db_client, clinician, survivor_id, encounter_id, body=body, key=key
    )
    assert created.status_code in {200, 201}
    replay_historical = await _create_note(
        db_client, clinician, source_id, encounter_id, body=body, key=key
    )
    assert replay_historical.status_code == 409
    assert replay_historical.json()["error"]["code"] == "idempotency_key_conflict"
    assert body not in replay_historical.text


@requires_db
async def test_replay_requires_current_facility_permission_and_purpose(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    facility_a = await _seed_facility(db_engine, clinician.organization_id, "HFA")
    facility_b = await _seed_facility(db_engine, clinician.organization_id, "HFB")
    bound_a = await _seed_facility_clinician(db_engine, clinician.organization_id, facility_a)
    patient_id = await _active_patient(db_client, registrar)
    encounter = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=note_write_headers(clinician, facility_id=facility_a, purpose="TREATMENT"),
        json={"patient_identity_id": patient_id, "encounter_class": "AMB"},
    )
    encounter_id = encounter.json()["id"]
    key = new_idempotency_key("fac-replay")
    created = await _create_note(
        db_client, bound_a, patient_id, encounter_id, body="Facility A note", key=key
    )
    assert created.status_code in {200, 201}

    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE organization_memberships SET facility_id = :fid WHERE user_id = :uid"),
            {"fid": facility_b, "uid": bound_a.user_id},
        )
    revoked = await _create_note(
        db_client, bound_a, patient_id, encounter_id, body="Facility A note", key=key
    )
    assert revoked.status_code == 403
    assert created.json()["id"] not in revoked.text
    assert "Facility A note" not in revoked.text

    perm_key = new_idempotency_key("perm-replay")
    permitted = await _create_note(
        db_client, clinician, patient_id, encounter_id, body="Permission note", key=perm_key
    )
    assert permitted.status_code in {200, 201}
    async with db_engine.begin() as connection:
        registrar_role = (
            await connection.execute(
                select(RoleModel.id).where(RoleModel.code == RoleCode.REGISTRAR)
            )
        ).scalar_one()
        await connection.execute(
            text("UPDATE organization_memberships SET role_id = :rid WHERE user_id = :uid"),
            {"rid": registrar_role, "uid": clinician.user_id},
        )
    lost_permission = await _create_note(
        db_client, clinician, patient_id, encounter_id, body="Permission note", key=perm_key
    )
    assert lost_permission.status_code == 403

    purpose_key = new_idempotency_key("purpose-replay")
    purpose_actor = await seed_actor(
        db_engine, role_code=RoleCode.CLINICIAN, organization_id=clinician.organization_id
    )
    original = await _create_note(
        db_client, purpose_actor, patient_id, encounter_id, body="Purpose note", key=purpose_key
    )
    assert original.status_code in {200, 201}
    missing_purpose = await db_client.post(
        "/api/v1/clinical/notes",
        headers={
            "Authorization": f"Bearer {purpose_actor.token}",
            "X-Organization-Id": str(purpose_actor.organization_id),
            "Idempotency-Key": purpose_key,
        },
        json=create_note_body(patient_id, encounter_id, body_text="Purpose note"),
    )
    assert missing_purpose.status_code == 422
    invalid_purpose = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(
            purpose_actor, purpose="NOT_A_PURPOSE", idempotency_key=purpose_key
        ),
        json=create_note_body(patient_id, encounter_id, body_text="Purpose note"),
    )
    assert invalid_purpose.status_code == 422
    administration = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(
            purpose_actor, purpose="ADMINISTRATION", idempotency_key=purpose_key
        ),
        json=create_note_body(patient_id, encounter_id, body_text="Purpose note"),
    )
    assert administration.status_code == 200
    assert administration.json()["id"] == original.json()["id"]


@requires_db
async def test_concurrent_same_key_different_payload_creates_at_most_one_note(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    key = new_idempotency_key("conflict-race")
    async with db_engine.connect() as connection:
        before = (
            await connection.execute(
                text("SELECT count(*) FROM clinical_notes WHERE author_id = :id"),
                {"id": clinician.user_id},
            )
        ).scalar_one()

    left, right = await asyncio.gather(
        _create_note(db_client, clinician, patient_id, encounter_id, body="Body one", key=key),
        _create_note(db_client, clinician, patient_id, encounter_id, body="Body two", key=key),
    )
    codes = sorted([left.status_code, right.status_code])
    assert codes[0] in {200, 201}
    assert codes[1] == 409
    conflict = left if left.status_code == 409 else right
    assert conflict.json()["error"]["code"] == "idempotency_key_conflict"
    assert "Body one" not in conflict.text
    assert "Body two" not in conflict.text
    async with db_engine.connect() as connection:
        after = (
            await connection.execute(
                text("SELECT count(*) FROM clinical_notes WHERE author_id = :id"),
                {"id": clinician.user_id},
            )
        ).scalar_one()
        mappings = (
            await connection.execute(
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
                    "key": key,
                },
            )
        ).scalar_one()
    assert after == before + 1
    assert mappings == 1


@requires_db
async def test_concurrent_same_key_finalize_replays_without_second_audit(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    created = await _create_note(db_client, clinician, patient_id, encounter_id, body="Sign race")
    note_id = created.json()["id"]
    key = new_idempotency_key("fin-race")

    async def finalize() -> object:
        return await db_client.post(
            f"/api/v1/clinical/notes/{note_id}/finalize",
            headers=note_write_headers(clinician, idempotency_key=key),
            json=finalize_note_body(patient_id),
        )

    left, right = await asyncio.gather(finalize(), finalize())
    assert sorted([left.status_code, right.status_code]) == [200, 200]
    assert left.json()["id"] == right.json()["id"] == note_id
    async with db_engine.connect() as connection:
        status = await connection.execute(
            text("SELECT record_status, version FROM clinical_notes WHERE id = :id"),
            {"id": note_id},
        )
        record_status, version = status.one()
        audits = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CLINICAL_NOTE_FINALIZED'
                """
            ),
            {"id": note_id},
        )
    assert record_status == "FINAL"
    assert version == 1
    assert audits.scalar_one() == 1


@requires_db
async def test_retired_identity_blocks_update_and_finalize(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    created = await _create_note(
        db_client, clinician, patient_id, encounter_id, body="Draft before retire"
    )
    note_id = created.json()["id"]
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": patient_id},
        )
    updated = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json=update_note_body(patient_id, 1, "should not save"),
    )
    assert updated.status_code == 409
    assert updated.json()["error"]["code"] == "identity_not_usable"
    assert "should not save" not in updated.text
    finalized = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}/finalize",
        headers=note_write_headers(clinician, idempotency_key=new_idempotency_key("retired-fin")),
        json=finalize_note_body(patient_id),
    )
    assert finalized.status_code == 409
    assert finalized.json()["error"]["code"] == "identity_not_usable"
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT body_text, record_status, version FROM clinical_notes WHERE id = :id"),
            {"id": note_id},
        )
        body_text, record_status, version = row.one()
        finals = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CLINICAL_NOTE_FINALIZED'
                """
            ),
            {"id": note_id},
        )
    assert body_text == "Draft before retire"
    assert record_status == "DRAFT"
    assert version == 1
    assert finals.scalar_one() == 0


@requires_db
async def test_planned_finished_body_semantics_and_idempotency_privacy(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    planned = await _open_encounter(db_client, clinician, patient_id)
    assert planned.json()["status"] == "PLANNED"
    planned_id = planned.json()["id"]
    planned_note = await _create_note(
        db_client, clinician, patient_id, planned_id, body="Planned encounter note"
    )
    assert planned_note.status_code in {200, 201}

    finishable = await _open_encounter(db_client, clinician, patient_id)
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
    finished_note = await _create_note(
        db_client, clinician, patient_id, finish_id, body="Finished encounter note"
    )
    assert finished_note.status_code in {200, 201}

    for body in ("\t\t", "\n\n", "   "):
        empty = await _create_note(db_client, clinician, patient_id, planned_id, body=body)
        assert empty.status_code == 422
        assert empty.json()["error"]["code"] == "note_body_required"

    padded = "  Stored assessment.  "
    pad_key = new_idempotency_key("pad")
    stored = await _create_note(
        db_client, clinician, patient_id, planned_id, body=padded, key=pad_key
    )
    assert stored.status_code in {200, 201}
    assert stored.json()["body_text"] == "Stored assessment."
    replay_stripped = await _create_note(
        db_client, clinician, patient_id, planned_id, body="Stored assessment.", key=pad_key
    )
    assert replay_stripped.status_code == 200
    assert replay_stripped.json()["id"] == stored.json()["id"]
    replay_padded = await _create_note(
        db_client, clinician, patient_id, planned_id, body=padded, key=pad_key
    )
    assert replay_padded.status_code == 200

    under = await _create_note(db_client, clinician, patient_id, planned_id, body="x" * 19999)
    limit = await _create_note(db_client, clinician, patient_id, planned_id, body="y" * 20000)
    over = await _create_note(db_client, clinician, patient_id, planned_id, body="z" * 20001)
    assert under.status_code in {200, 201}
    assert limit.status_code in {200, 201}
    assert len(under.json()["body_text"]) == 19999
    assert len(limit.json()["body_text"]) == 20000
    assert over.status_code == 422
    assert "zzz" not in over.text

    unicode_body = "Nyeri dada. 胸痛评估。e\u0301 ⚠️"
    unicode_key = new_idempotency_key("unicode")
    unicode_note = await _create_note(
        db_client, clinician, patient_id, planned_id, body=unicode_body, key=unicode_key
    )
    assert unicode_note.status_code in {200, 201}
    assert unicode_note.json()["body_text"] == unicode_body
    unicode_replay = await _create_note(
        db_client, clinician, patient_id, planned_id, body=unicode_body, key=unicode_key
    )
    assert unicode_replay.status_code == 200
    assert unicode_replay.json()["id"] == unicode_note.json()["id"]

    async with db_engine.connect() as connection:
        columns = await connection.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'clinical_note_write_idempotency'
                """
            )
        )
        names = {row[0] for row in columns}
        row = await connection.execute(
            text(
                """
                SELECT organization_id, actor_id, operation, idempotency_key,
                       request_fingerprint, note_id
                FROM clinical_note_write_idempotency
                WHERE note_id = :id
                """
            ),
            {"id": stored.json()["id"]},
        )
        mapping = row.one()
    assert names == {
        "id",
        "organization_id",
        "actor_id",
        "operation",
        "idempotency_key",
        "request_fingerprint",
        "note_id",
        "created_at",
    }
    assert mapping.request_fingerprint != padded
    assert "Stored assessment" not in mapping.request_fingerprint
    assert len(mapping.request_fingerprint) == 64
    assert mapping.operation == "NOTE_CREATE"
    dumped = " ".join(str(item) for item in mapping)
    assert "Nyeri" not in dumped
    assert "Stored assessment" not in dumped


@requires_db
async def test_update_finalize_facility_matrix_and_get_note_isolation(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    facility_a = await _seed_facility(db_engine, clinician.organization_id, "UFA")
    facility_b = await _seed_facility(db_engine, clinician.organization_id, "UFB")
    bound_b = await _seed_facility_clinician(db_engine, clinician.organization_id, facility_b)
    patient_id = await _active_patient(db_client, registrar)
    encounter_a = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=note_write_headers(clinician, facility_id=facility_a, purpose="TREATMENT"),
        json={"patient_identity_id": patient_id, "encounter_class": "AMB"},
    )
    encounter_a_id = encounter_a.json()["id"]
    created = await _create_note(
        db_client, clinician, patient_id, encounter_a_id, facility_id=facility_a
    )
    note_id = created.json()["id"]

    match = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=note_write_headers(clinician, facility_id=facility_a, purpose="TREATMENT"),
        json=update_note_body(patient_id, 1, "updated at A"),
    )
    assert match.status_code == 200
    mismatch = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=note_write_headers(clinician, facility_id=facility_b, purpose="TREATMENT"),
        json=update_note_body(patient_id, 2, "should not write"),
    )
    assert mismatch.status_code == 409
    absent_ok = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json=update_note_body(patient_id, 2, "org-wide update"),
    )
    assert absent_ok.status_code == 200
    absent_denied = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=bound_b.headers(purpose="TREATMENT"),
        json=update_note_body(patient_id, 3, "scoped B"),
    )
    assert absent_denied.status_code == 403

    finalize_mismatch = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}/finalize",
        headers=note_write_headers(
            clinician, facility_id=facility_b, idempotency_key=new_idempotency_key("fin-b")
        ),
        json=finalize_note_body(patient_id),
    )
    assert finalize_mismatch.status_code == 409
    finalize_denied = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}/finalize",
        headers=note_write_headers(bound_b, idempotency_key=new_idempotency_key("fin-denied")),
        json=finalize_note_body(patient_id),
    )
    assert finalize_denied.status_code == 403
    finalize_ok = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}/finalize",
        headers=note_write_headers(
            clinician, facility_id=facility_a, idempotency_key=new_idempotency_key("fin-a")
        ),
        json=finalize_note_body(patient_id),
    )
    assert finalize_ok.status_code == 200
    async with db_engine.connect() as connection:
        facility = await connection.execute(
            text("SELECT facility_id FROM clinical_notes WHERE id = :id"),
            {"id": note_id},
        )
        assert str(facility.scalar_one()) == str(facility_a)

    null_encounter = await _open_encounter(db_client, clinician, patient_id)
    null_note = await _create_note(db_client, clinician, patient_id, null_encounter.json()["id"])
    null_id = null_note.json()["id"]
    null_header = await db_client.post(
        f"/api/v1/clinical/notes/{null_id}",
        headers=note_write_headers(clinician, facility_id=facility_a, purpose="TREATMENT"),
        json=update_note_body(patient_id, 1, "null facility update"),
    )
    assert null_header.status_code == 200
    null_absent = await db_client.post(
        f"/api/v1/clinical/notes/{null_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json=update_note_body(patient_id, 2, "null facility absent"),
    )
    assert null_absent.status_code == 200

    fetched = await db_client.get(
        f"/api/v1/clinical/notes/{note_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.status_code == 200
    assert fetched.json()["body_text"] == "org-wide update"
    cross = await db_client.get(
        f"/api/v1/clinical/notes/{note_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "org-wide update" not in cross.text


@requires_db
async def test_foreign_expected_identity_does_not_canonicalize_into_local_write(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    foreign = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    local_patient = await _active_patient(db_client, registrar)
    foreign_patient = await _active_patient(db_client, foreign)
    encounter_id = (await _open_encounter(db_client, clinician, local_patient)).json()["id"]
    async with db_engine.connect() as connection:
        before = (
            await connection.execute(text("SELECT count(*) FROM clinical_notes"))
        ).scalar_one()
    hop = await _create_note(db_client, clinician, foreign_patient, encounter_id)
    assert hop.status_code == 404
    async with db_engine.connect() as connection:
        after = (await connection.execute(text("SELECT count(*) FROM clinical_notes"))).scalar_one()
    assert after == before


def test_migration_0019_revises_0018_without_privilege_grants() -> None:
    migration = (
        BACKEND_ROOT / "alembic" / "versions" / "20260814_0019_clinical_note_write_idempotency.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20260814_0018"' in migration
    assert "clinical_note_write_idempotency" in migration
    assert "prevent_clinical_note_write_idempotency_mutation" in migration
    assert "clinical note attribution is immutable" in migration
    assert "GRANT " not in migration
    assert "0020" not in migration
    assert 'op.drop_table("clinical_note_write_idempotency")' in migration


@requires_db
async def test_zz_migration_0019_downgrade_upgrade_roundtrip(db_engine) -> None:
    env = os.environ.copy()
    url = (
        env.get("DATABASE_MIGRATION_URL") or env.get("TEST_DATABASE_URL") or env.get("DATABASE_URL")
    )
    assert url
    env["DATABASE_MIGRATION_URL"] = url
    env["DATABASE_URL"] = url

    def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    try:
        downgrade = await asyncio.to_thread(run_alembic, "downgrade", "20260814_0018")
        assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
        async with db_engine.connect() as connection:
            version = await connection.execute(text("SELECT version_num FROM alembic_version"))
            assert version.scalar_one() == "20260814_0018"
            tables = await connection.execute(
                text(
                    """
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'clinical_note_write_idempotency'
                    """
                )
            )
            assert tables.scalar_one() == 0
            notes = await connection.execute(
                text(
                    """
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'clinical_notes'
                    """
                )
            )
            assert notes.scalar_one() == 1
    finally:
        upgrade = await asyncio.to_thread(run_alembic, "upgrade", "head")
        assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    async with db_engine.connect() as connection:
        version = await connection.execute(text("SELECT version_num FROM alembic_version"))
        assert version.scalar_one() == "20260814_0021"
        tables = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'clinical_note_write_idempotency'
                """
            )
        )
        assert tables.scalar_one() == 1
        observation_tables = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'clinical_observation_write_idempotency'
                """
            )
        )
        assert observation_tables.scalar_one() == 1
        heads = await connection.execute(text("SELECT count(*) FROM alembic_version"))
        assert heads.scalar_one() == 1
    await restore_note_write_idempotency_app_dml_privileges(db_engine)
