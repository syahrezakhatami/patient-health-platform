import asyncio
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.infrastructure.models import OrganizationMembershipModel, RoleModel, UserModel
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel
from app.shared.types.ids import new_id
from sqlalchemy import select, text
from tests.conftest import mint_token
from tests.integration.clinical_notes import (
    create_note_body,
    finalize_note_body,
    new_idempotency_key,
    note_write_headers,
    update_note_body,
)
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave15_hardening import _headers

pytestmark = [pytest.mark.integration]


async def _active_patient(db_client, registrar: SeededActor) -> str:
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    assert created.status_code in {200, 201}
    return created.json()["id"]


async def _open_encounter(db_client, clinician: SeededActor, patient_id: str, klass: str = "AMB"):
    response = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"patient_identity_id": patient_id, "encounter_class": klass},
    )
    return response


@requires_db
async def test_identity_binding_for_lifecycle_states(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    active_id = await _active_patient(db_client, registrar)
    active = await _open_encounter(db_client, clinician, active_id)
    assert active.status_code in {200, 201}
    assert active.json()["patient_identity_id"] == active_id

    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=registrar.headers(purpose="EMERGENCY"),
        json={},
    )
    anonymous_id = anonymous.json()["id"]
    blocked_amb = await _open_encounter(db_client, clinician, anonymous_id, "AMB")
    assert blocked_amb.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    assert emer.status_code in {200, 201}

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
                    "identifier_value": unique_mrn("W2A"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Merge", family="Survivor", birth="1977-07-07"),
    )
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2A identity binding",
            "evidence": merge_evidence("wave2a-bind"),
        },
    )
    assert merged.status_code in {200, 201}
    resolved = await _open_encounter(db_client, clinician, source.json()["id"])
    assert resolved.status_code in {200, 201}
    assert resolved.json()["patient_identity_id"] == survivor.json()["id"]

    retired = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    rejected = await _open_encounter(db_client, clinician, retired)
    assert rejected.status_code == 409
    missing = await _open_encounter(db_client, clinician, str(uuid4()))
    assert missing.status_code == 404


@requires_db
async def test_encounter_status_machine_and_completed_alias_rejected(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await _open_encounter(db_client, clinician, patient_id)
    encounter_id = created.json()["id"]
    assert created.json()["status"] == "PLANNED"
    started = await db_client.post(
        f"/api/v1/clinical/encounters/{encounter_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "IN_PROGRESS"},
    )
    assert started.status_code == 200
    illegal = await db_client.post(
        f"/api/v1/clinical/encounters/{encounter_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "PLANNED"},
    )
    assert illegal.status_code == 409
    invented = await db_client.post(
        f"/api/v1/clinical/encounters/{encounter_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "COMPLETED"},
    )
    assert invented.status_code == 422
    finished = await db_client.post(
        f"/api/v1/clinical/encounters/{encounter_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "FINISHED"},
    )
    assert finished.status_code == 200
    assert finished.json()["status"] == "FINISHED"


@requires_db
async def test_purpose_does_not_grant_clinical_access(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await _open_encounter(db_client, clinician, patient_id)
    encounter_id = created.json()["id"]
    valid_unauth = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(registrar, idempotency_key=new_idempotency_key("unauth")),
        json=create_note_body(patient_id, encounter_id, body_text="bypass?"),
    )
    assert valid_unauth.status_code == 403
    assert "bypass?" not in valid_unauth.text
    invalid = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers=clinician.headers(purpose="billing"),
    )
    assert invalid.status_code == 422


@requires_db
async def test_note_immutability_api_and_database(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    note = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(clinician, idempotency_key=new_idempotency_key("immut")),
        json=create_note_body(patient_id, encounter_id, body_text="draft body"),
    )
    note_id = note.json()["id"]
    assert note.json()["version"] == 1
    updated = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json=update_note_body(patient_id, 1, "edited draft"),
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    finalized = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}/finalize",
        headers=note_write_headers(clinician, idempotency_key=new_idempotency_key("immut-fin")),
        json=finalize_note_body(patient_id),
    )
    assert finalized.status_code == 200
    blocked = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json=update_note_body(patient_id, 2, "overwrite final"),
    )
    assert blocked.status_code == 409
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE clinical_notes SET body_text = 'sql overwrite' WHERE id = :id"),
                    {"id": note_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE clinical_notes SET author_id = :aid WHERE id = :id"),
                    {"id": note_id, "aid": uuid4()},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE clinical_notes SET record_status = 'DRAFT' WHERE id = :id"),
                    {"id": note_id},
                )
        with pytest.raises(Exception, match="cannot be deleted|permission denied"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM clinical_notes WHERE id = :id"), {"id": note_id}
                )
    marked = await db_client.post(
        f"/api/v1/clinical/notes/{note_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert marked.status_code == 200
    assert marked.json()["record_status"] == "ENTERED_IN_ERROR"
    async with db_engine.connect() as connection:
        audit = await connection.execute(
            text(
                """
                SELECT action, metadata::text
                FROM audit_events
                WHERE resource_id = :id
                """
            ),
            {"id": note_id},
        )
        rows = list(audit)
        actions = {row[0] for row in rows}
        assert "CLINICAL_NOTE_FINALIZED" in actions
        assert "CLINICAL_NOTE_ENTERED_IN_ERROR" in actions
        assert all("edited draft" not in (row[1] or "") for row in rows)
        assert all("overwrite final" not in (row[1] or "") for row in rows)


@requires_db
async def test_encounter_cannot_be_hard_deleted(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="cannot be deleted|permission denied"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM encounters WHERE id = :id"), {"id": encounter_id}
                )
    gone = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert gone.status_code == 200


@requires_db
async def test_concurrent_note_finalize_and_status_change(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    started = await db_client.post(
        f"/api/v1/clinical/encounters/{encounter_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "IN_PROGRESS"},
    )
    assert started.status_code == 200
    note = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(clinician, idempotency_key=new_idempotency_key("race")),
        json=create_note_body(patient_id, encounter_id, body_text="race note"),
    )
    note_id = note.json()["id"]

    async def finalize() -> object:
        return await db_client.post(
            f"/api/v1/clinical/notes/{note_id}/finalize",
            headers=note_write_headers(clinician, idempotency_key=new_idempotency_key("race-fin")),
            json=finalize_note_body(patient_id),
        )

    first, second = await asyncio.gather(finalize(), finalize())
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409]
    async with db_engine.connect() as connection:
        status = await connection.execute(
            text("SELECT record_status FROM clinical_notes WHERE id = :id"),
            {"id": note_id},
        )
        assert status.scalar_one() == "FINAL"
        finals = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CLINICAL_NOTE_FINALIZED'
                """
            ),
            {"id": note_id},
        )
        assert finals.scalar_one() == 1

    async def finish() -> object:
        return await db_client.post(
            f"/api/v1/clinical/encounters/{encounter_id}/status",
            headers=clinician.headers(purpose="TREATMENT"),
            json={"status": "FINISHED"},
        )

    async def cancel() -> object:
        return await db_client.post(
            f"/api/v1/clinical/encounters/{encounter_id}/status",
            headers=clinician.headers(purpose="TREATMENT"),
            json={"status": "CANCELLED"},
        )

    left, right = await asyncio.gather(finish(), cancel())
    outcome = {left.status_code, right.status_code}
    assert 200 in outcome
    assert 409 in outcome
    async with db_engine.connect() as connection:
        current = await connection.execute(
            text("SELECT status FROM encounters WHERE id = :id"),
            {"id": encounter_id},
        )
        assert current.scalar_one() in {"FINISHED", "CANCELLED"}


@requires_db
async def test_clinical_idor_and_facility_scope(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    note = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(clinician, idempotency_key=new_idempotency_key("idor")),
        json=create_note_body(patient_id, encounter_id, body_text="org a note"),
    )
    note_id = note.json()["id"]
    cross_note = await db_client.get(
        f"/api/v1/clinical/notes/{note_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross_note.status_code == 404
    assert "sqlalchemy" not in cross_note.text.lower()
    assert "org a note" not in cross_note.text
    unknown_note = await db_client.get(
        f"/api/v1/clinical/notes/{uuid4()}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unknown_note.status_code == 404
    unprovisioned = mint_token(sub="nobody-clinical")
    denied = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers={
            "Authorization": f"Bearer {unprovisioned}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert denied.status_code == 403

    in_scope = new_id()
    out_of_scope = new_id()
    async with db_engine.begin() as connection:
        for facility_id, code in ((in_scope, "CIN"), (out_of_scope, "COUT")):
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
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers=_headers(bound, "TREATMENT", str(in_scope)),
    )
    assert allowed.status_code == 200
    facility_denied = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers=_headers(bound, "TREATMENT", str(out_of_scope)),
    )
    assert facility_denied.status_code == 403
    empty_binding = await db_client.get(
        f"/api/v1/clinical/encounters/{encounter_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert empty_binding.status_code == 200
