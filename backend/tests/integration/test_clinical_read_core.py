from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.clinical.infrastructure.models import ClinicalProvenanceModel
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.infrastructure.models import (
    OrganizationMembershipModel,
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
)
from app.modules.mpi.domain.enums import ProvenanceSubjectType
from app.modules.mpi.infrastructure.models import IdentityProvenanceModel
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel
from app.shared.enums import AuthorshipKind, InformationSource
from app.shared.types.ids import new_id
from sqlalchemy import func, select, text
from tests.conftest import mint_token
from tests.integration.clinical_notes import (
    create_note_body,
    new_idempotency_key,
    note_write_headers,
)
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave2b1_condition import _pneumonia
from tests.integration.test_wave2b2a_observation import _generic_exam_observation
from tests.integration.test_wave2b3a_medication import _paracetamol
from tests.integration.test_wave2b3b_allergy import _penicillin

pytestmark = pytest.mark.integration


def _chart(patient_id: str, suffix: str = "") -> str:
    return f"/api/v1/clinical/patients/{patient_id}/chart{suffix}"


def _staff_headers(actor: SeededActor, purpose: str = "TREATMENT") -> dict[str, str]:
    return actor.headers(purpose=purpose)


async def _seed_limited(
    engine,
    organization_id,
    permission_codes: tuple[str, ...],
) -> SeededActor:
    subject = f"user-{new_id()}"
    user_id = new_id()
    role_id = new_id()
    async with engine.begin() as connection:
        await connection.execute(
            RoleModel.__table__.insert().values(
                id=role_id,
                code=f"LIM{role_id.hex[:10].upper()}",
                name="Limited reader",
            )
        )
        permission_ids = (
            (
                await connection.execute(
                    select(PermissionModel.id).where(PermissionModel.code.in_(permission_codes))
                )
            )
            .scalars()
            .all()
        )
        for permission_id in permission_ids:
            await connection.execute(
                RolePermissionModel.__table__.insert().values(
                    id=new_id(),
                    role_id=role_id,
                    permission_id=permission_id,
                )
            )
        await connection.execute(
            UserModel.__table__.insert().values(
                id=user_id,
                subject=subject,
                display_name=subject,
                status=UserStatus.ACTIVE,
            )
        )
        await connection.execute(
            OrganizationMembershipModel.__table__.insert().values(
                id=new_id(),
                user_id=user_id,
                organization_id=organization_id,
                facility_id=None,
                role_id=role_id,
                status=MembershipStatus.ACTIVE,
            )
        )
    return SeededActor(user_id, subject, organization_id, mint_token(sub=subject))


@requires_db
async def test_clinical_read_core_chart_cluster_authz_and_notes(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    auditor = await seed_actor(
        db_engine, role_code=RoleCode.AUDITOR, organization_id=clinician.organization_id
    )
    org_admin = await seed_actor(
        db_engine, role_code=RoleCode.ORG_ADMIN, organization_id=clinician.organization_id
    )
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    officer_b = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=hospital_b.organization_id
    )
    mrn = unique_mrn("CRC")
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Read",
            "family_name": "Source",
            "birth_date": "1990-08-26",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": mrn,
                }
            ],
        },
    )
    assert source.status_code in {200, 201}
    source_id = source.json()["id"]
    historical = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(source_id),
    )
    assert historical.status_code in {200, 201}
    historical_id = historical.json()["id"]
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Read", family="Survivor", birth="1990-08-26"),
    )
    survivor_id = survivor.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source_id,
            "target_identity_id": survivor_id,
            "reason": "Clinical read cluster",
            "evidence": merge_evidence("crc-cluster"),
        },
    )
    assert merged.status_code in {200, 201}
    current = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(survivor_id),
    )
    assert current.status_code in {200, 201}
    current_id = current.json()["id"]
    allergy = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(survivor_id),
    )
    assert allergy.status_code in {200, 201}
    encounter = await _open_encounter(db_client, clinician, survivor_id)
    encounter_id = encounter.json()["id"]
    note = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(clinician, idempotency_key=new_idempotency_key("crc")),
        json=create_note_body(
            survivor_id,
            encounter_id,
            body_text="Secret note body must not appear in list DTO",
        ),
    )
    assert note.status_code in {200, 201}
    note_id = note.json()["id"]
    await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(survivor_id),
    )
    await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_generic_exam_observation(survivor_id, encounter_id),
    )
    async with db_engine.begin() as connection:
        await connection.execute(
            IdentityProvenanceModel.__table__.insert().values(
                id=new_id(),
                subject_type=ProvenanceSubjectType.PATIENT_IDENTITY,
                subject_id=survivor_id,
                source_organization_id=hospital_b.organization_id,
                source_facility_id=None,
                source_system=None,
                source_record_id=None,
                actor_id=officer_b.user_id,
                recorded_at=datetime.now(UTC),
                imported_at=None,
                verification_method=None,
                authorship_kind=AuthorshipKind.NATIVE,
                information_source=InformationSource.CLINICIAN,
            )
        )
    foreign_fact = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=hospital_b.headers(purpose="TREATMENT"),
        json=_pneumonia(survivor_id),
    )
    assert foreign_fact.status_code in {200, 201}
    foreign_id = foreign_fact.json()["id"]

    async with db_engine.connect() as connection:
        provenance_before = (
            await connection.execute(select(func.count()).select_from(ClinicalProvenanceModel))
        ).scalar_one()

    shell = await db_client.get(
        _chart(source_id),
        headers=_staff_headers(clinician),
    )
    assert shell.status_code == 200
    body = shell.json()
    assert body["canonical_patient_identity_id"] == survivor_id
    assert body["requested_patient_identity_id"] == source_id
    assert body["header"]["canonical_patient_identity_id"] == survivor_id
    assert body["header"]["age_years"] is not None
    assert mrn in body["header"]["mrn"]
    assert "nik" not in shell.text.lower()
    assert "bpjs" not in shell.text.lower()
    assert body["header"]["documented_allergy_exists"] is True
    assert "encounters" in body["authorized_sections"]
    assert "conditions" in body["authorized_sections"]

    conditions = await db_client.get(
        _chart(survivor_id, "/sections/conditions"),
        headers=_staff_headers(clinician),
    )
    assert conditions.status_code == 200
    condition_ids = {item["id"] for item in conditions.json()["items"]}
    assert historical_id in condition_ids
    assert current_id in condition_ids
    assert foreign_id not in condition_ids
    assert len(condition_ids) == len(conditions.json()["items"])

    paged = await db_client.get(
        _chart(survivor_id, "/sections/conditions"),
        headers=_staff_headers(clinician),
        params={"limit": 1},
    )
    assert paged.status_code == 200
    assert len(paged.json()["items"]) == 1
    assert paged.json()["has_more"] is True
    assert paged.json()["next_cursor"]

    b_conditions = await db_client.get(
        _chart(survivor_id, "/sections/conditions"),
        headers=_staff_headers(hospital_b),
    )
    assert b_conditions.status_code == 200
    b_ids = {item["id"] for item in b_conditions.json()["items"]}
    assert foreign_id in b_ids
    assert historical_id not in b_ids
    assert current_id not in b_ids

    registrar_shell = await db_client.get(
        _chart(survivor_id),
        headers=_staff_headers(registrar, "REGISTRATION"),
    )
    assert registrar_shell.status_code == 200
    assert registrar_shell.json()["authorized_sections"] == ["encounters"]
    assert "documented_allergy_exists" not in registrar_shell.json()["header"]
    registrar_conditions = await db_client.get(
        _chart(survivor_id, "/sections/conditions"),
        headers=_staff_headers(registrar, "REGISTRATION"),
    )
    assert registrar_conditions.status_code == 403
    registrar_encounters = await db_client.get(
        _chart(survivor_id, "/sections/encounters"),
        headers=_staff_headers(registrar, "REGISTRATION"),
    )
    assert registrar_encounters.status_code == 200

    officer_shell = await db_client.get(
        _chart(survivor_id),
        headers=_staff_headers(officer, "IDENTITY_RESOLUTION"),
    )
    assert officer_shell.status_code == 200
    assert officer_shell.json()["authorized_sections"] == []
    officer_encounters = await db_client.get(
        _chart(survivor_id, "/sections/encounters"),
        headers=_staff_headers(officer, "IDENTITY_RESOLUTION"),
    )
    assert officer_encounters.status_code == 403

    for actor, purpose in ((auditor, "AUDIT"), (org_admin, "ADMINISTRATION")):
        visible = await db_client.get(
            _chart(survivor_id, "/sections/conditions"),
            headers=_staff_headers(actor, purpose),
        )
        assert visible.status_code == 200

    notes = await db_client.get(
        _chart(survivor_id, "/sections/notes"),
        headers=_staff_headers(clinician),
    )
    assert notes.status_code == 200
    assert notes.json()["items"][0]["id"] == note_id
    assert "body_text" not in notes.json()["items"][0]
    assert "Secret note body" not in notes.text
    full_note = await db_client.get(
        f"/api/v1/clinical/notes/{note_id}",
        headers=_staff_headers(clinician),
    )
    assert full_note.status_code == 200
    assert "Secret note body" in full_note.json()["body_text"]

    encounter_notes = await db_client.get(
        _chart(survivor_id, "/sections/notes"),
        headers=_staff_headers(clinician),
        params={"encounter_id": encounter_id},
    )
    assert encounter_notes.status_code == 200
    unknown_encounter = await db_client.get(
        _chart(survivor_id, "/sections/notes"),
        headers=_staff_headers(clinician),
        params={"encounter_id": str(uuid4())},
    )
    assert unknown_encounter.status_code == 404

    summary = await db_client.get(
        _chart(survivor_id, "/summary"),
        headers=_staff_headers(clinician),
    )
    assert summary.status_code == 200
    assert len(summary.json()["active_conditions"]) <= 10
    assert all("source_id" in item for item in summary.json()["active_conditions"])
    summary_encounter = await db_client.get(
        _chart(survivor_id, "/summary"),
        headers=_staff_headers(clinician),
        params={"encounter_id": encounter_id},
    )
    assert summary_encounter.status_code == 200

    timeline = await db_client.get(
        _chart(survivor_id, "/timeline"),
        headers=_staff_headers(clinician),
        params={"limit": 1},
    )
    assert timeline.status_code == 200
    assert len(timeline.json()["items"]) == 1
    assert timeline.json()["has_more"] is True
    assert "body_text" not in timeline.json()["items"][0]
    second = await db_client.get(
        _chart(survivor_id, "/timeline"),
        headers=_staff_headers(clinician),
        params={"limit": 1, "cursor": timeline.json()["next_cursor"]},
    )
    assert second.status_code == 200
    assert second.json()["items"][0]["source_id"] != timeline.json()["items"][0]["source_id"]
    bad_cursor = await db_client.get(
        _chart(survivor_id, "/timeline"),
        headers=_staff_headers(clinician),
        params={"cursor": "%%%"},
    )
    assert bad_cursor.status_code == 422

    observations_section = await db_client.get(
        _chart(survivor_id, "/sections/observations"),
        headers=_staff_headers(clinician),
        params={"category": "EXAM"},
    )
    assert observations_section.status_code == 200
    assert observations_section.json()["items"]

    unknown_section = await db_client.get(
        _chart(survivor_id, "/sections/vitals"),
        headers=_staff_headers(clinician),
    )
    assert unknown_section.status_code == 404

    missing_purpose = await db_client.get(
        _chart(survivor_id),
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
    )
    assert missing_purpose.status_code == 422
    patient_access = await db_client.get(
        _chart(survivor_id),
        headers=_staff_headers(clinician, "PATIENT_ACCESS"),
    )
    assert patient_access.status_code == 403
    assert patient_access.json()["error"]["code"] == "purpose_principal_mismatch"

    unknown = await db_client.get(
        _chart(str(uuid4())),
        headers=_staff_headers(clinician),
    )
    assert unknown.status_code == 404
    outsider = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    outsider_chart = await db_client.get(
        _chart(survivor_id),
        headers=_staff_headers(outsider),
    )
    assert outsider_chart.status_code == 404

    retired = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    retired_chart = await db_client.get(_chart(retired), headers=_staff_headers(clinician))
    assert retired_chart.status_code == 409

    patient_token = mint_token(sub=f"patient-{uuid4()}", aud="php-patient")
    patient_denied = await db_client.get(
        _chart(survivor_id),
        headers={
            "Authorization": f"Bearer {patient_token}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert patient_denied.status_code == 401
    platform_token = mint_token(sub=f"platform-{uuid4()}", aud="php-platform")
    platform_denied = await db_client.get(
        _chart(survivor_id),
        headers={
            "Authorization": f"Bearer {platform_token}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert platform_denied.status_code == 401

    async with db_engine.connect() as connection:
        provenance_after = (
            await connection.execute(select(func.count()).select_from(ClinicalProvenanceModel))
        ).scalar_one()
        audits = (
            (
                await connection.execute(
                    text(
                        "SELECT action, metadata FROM audit_events "
                        "WHERE action = 'CLINICAL_CHART_ACCESSED' "
                        "AND patient_id = :pid"
                    ),
                    {"pid": survivor_id},
                )
            )
            .mappings()
            .all()
        )
    assert provenance_after == provenance_before
    surfaces = {row["metadata"].get("surface") for row in audits}
    assert {"shell", "summary", "timeline"} <= surfaces
    for row in audits:
        blob = str(row["metadata"]).lower()
        assert "nik" not in blob
        assert "bpjs" not in blob
        assert "secret note body" not in blob
        assert "bearer" not in blob


@requires_db
async def test_clinical_read_core_limited_permissions_and_facility(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id),
    )
    limited = await _seed_limited(
        db_engine,
        clinician.organization_id,
        (
            Permission.MPI_IDENTITY_READ,
            Permission.IAM_USER_READ,
            Permission.ORG_ORGANIZATION_READ,
            Permission.CLINICAL_CONDITION_READ,
            Permission.CLINICAL_OBSERVATION_READ,
            Permission.CLINICAL_MEDICATION_READ,
        ),
    )
    shell = await db_client.get(_chart(patient_id), headers=_staff_headers(limited))
    assert shell.status_code == 200
    sections = shell.json()["authorized_sections"]
    assert "conditions" in sections
    assert "observations" in sections
    assert "medications" in sections
    assert "allergies" not in sections
    assert "laboratory" not in sections
    assert "documented_allergy_exists" not in shell.json()["header"]
    forbidden = await db_client.get(
        _chart(patient_id, "/sections/allergies"),
        headers=_staff_headers(limited),
    )
    assert forbidden.status_code == 403
    allowed = await db_client.get(
        _chart(patient_id, "/sections/conditions"),
        headers=_staff_headers(limited),
    )
    assert allowed.status_code == 200

    facility_id = new_id()
    foreign_facility = new_id()
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    async with db_engine.begin() as connection:
        await connection.execute(
            FacilityModel.__table__.insert().values(
                id=facility_id,
                organization_id=clinician.organization_id,
                name="Ward A",
                code=f"WA{facility_id.hex[:6].upper()}",
                facility_type=FacilityType.CLINIC_SITE,
                status=FacilityStatus.ACTIVE,
            )
        )
        await connection.execute(
            FacilityModel.__table__.insert().values(
                id=foreign_facility,
                organization_id=other.organization_id,
                name="Ward B",
                code=f"WB{foreign_facility.hex[:6].upper()}",
                facility_type=FacilityType.CLINIC_SITE,
                status=FacilityStatus.ACTIVE,
            )
        )
    filtered = await db_client.get(
        _chart(patient_id, "/sections/conditions"),
        headers=_staff_headers(clinician),
        params={"facility_id": str(facility_id)},
    )
    assert filtered.status_code == 200
    concealed = await db_client.get(
        _chart(patient_id, "/sections/conditions"),
        headers=_staff_headers(clinician),
        params={"facility_id": str(foreign_facility)},
    )
    assert concealed.status_code == 404
    header_foreign = await db_client.get(
        _chart(patient_id),
        headers={
            **_staff_headers(clinician),
            "X-Facility-Id": str(foreign_facility),
        },
    )
    assert header_foreign.status_code == 404

    frozen_list = await db_client.get(
        "/api/v1/clinical/conditions",
        headers=_staff_headers(clinician),
        params={"patient_identity_id": patient_id},
    )
    assert frozen_list.status_code == 200
