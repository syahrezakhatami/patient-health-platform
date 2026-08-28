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


def _penicillin(
    patient_id: str,
    encounter_id: str | None = None,
    *,
    severity: str | None = "SEVERE",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "patient_identity_id": patient_id,
        "category": "DRUG",
        "code": {"system": SNOMED, "code": "373270004", "display": "Penicillin"},
        "clinical_status": "ACTIVE",
        "verification_status": "CONFIRMED",
        "criticality": "HIGH",
        "reaction": {"system": SNOMED, "code": "39579001", "display": "Anaphylaxis"},
    }
    if severity is not None:
        payload["severity"] = severity
    if encounter_id is not None:
        payload["encounter_id"] = encounter_id
    return payload


def _amend_body(
    *, clinical: str = "INACTIVE", verification: str = "CONFIRMED"
) -> dict[str, object]:
    return {
        "clinical_status": clinical,
        "verification_status": verification,
        "criticality": "LOW",
        "severity": "MILD",
        "reaction": {"system": SNOMED, "code": "271807003", "display": "Rash"},
    }


@requires_db
async def test_allergy_lifecycle_identity_and_authorization(db_client, db_engine) -> None:
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
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]

    invalid = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_penicillin(patient_id), "category": "NOT_A_CATEGORY"},
    )
    assert invalid.status_code == 422
    invalid_verification = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_penicillin(patient_id), "verification_status": "ENTERED_IN_ERROR"},
    )
    assert invalid_verification.status_code == 422
    invalid_allergen = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_penicillin(patient_id), "code": {"system": "", "code": "373270004"}},
    )
    assert invalid_allergen.status_code == 422

    created = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id, encounter_id),
    )
    assert created.status_code in {200, 201}
    body = created.json()
    assert body["status"] == "ACTIVE"
    assert body["clinical_status"] == "ACTIVE"
    assert body["verification_status"] == "CONFIRMED"
    assert body["version"] == 1
    assert body["category"] == "DRUG"
    allergy_id = body["id"]

    denied = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id),
    )
    assert denied.status_code == 403
    assert "Penicillin" not in denied.text
    assert "Anaphylaxis" not in denied.text

    listed = await db_client.get(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert listed.status_code == 200
    assert allergy_id in {item["id"] for item in listed.json()}

    auditor_read = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=auditor.headers(purpose="AUDIT"),
    )
    assert auditor_read.status_code == 200
    admin_create = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id),
    )
    assert admin_create.status_code == 403
    admin_read = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=org_admin.headers(purpose="TREATMENT"),
    )
    assert admin_read.status_code == 200
    platform_read = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=platform.headers(purpose="TREATMENT"),
    )
    assert platform_read.status_code == 403

    amended = await db_client.post(
        f"/api/v1/clinical/allergies/{allergy_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(),
    )
    assert amended.status_code == 200
    assert amended.json()["status"] == "AMENDED"
    assert amended.json()["clinical_status"] == "INACTIVE"
    assert amended.json()["severity"] == "MILD"
    assert amended.json()["version"] == 2
    noop = await db_client.post(
        f"/api/v1/clinical/allergies/{allergy_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(),
    )
    assert noop.status_code == 409

    voided = await db_client.post(
        f"/api/v1/clinical/allergies/{allergy_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    blocked = await db_client.post(
        f"/api/v1/clinical/allergies/{allergy_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_amend_body(clinical="ACTIVE"),
    )
    assert blocked.status_code == 409
    blocked_eie = await db_client.post(
        f"/api/v1/clinical/allergies/{allergy_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_eie.status_code == 409

    cross = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "sqlalchemy" not in cross.text.lower()
    assert "373270004" not in cross.text
    assert "Penicillin" not in cross.text
    unknown = await db_client.get(
        f"/api/v1/clinical/allergies/{uuid4()}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unknown.status_code == 404
    deleted = await db_client.delete(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
    put = await db_client.put(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={},
    )
    assert put.status_code == 405
    missing_purpose = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
    )
    assert missing_purpose.status_code == 422
    invalid_purpose = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=clinician.headers(purpose="NOT_A_PURPOSE"),
    )
    assert invalid_purpose.status_code == 422
    unauthenticated = await db_client.get(f"/api/v1/clinical/allergies/{allergy_id}")
    assert unauthenticated.status_code == 401
    unauthenticated_post = await db_client.post(
        "/api/v1/clinical/allergies",
        json=_penicillin(patient_id),
    )
    assert unauthenticated_post.status_code == 401
    unprovisioned = mint_token(sub="nobody-allergy")
    denied_jwt = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
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
                    text("UPDATE allergies SET patient_identity_id = :pid WHERE id = :id"),
                    {"id": allergy_id, "pid": uuid4()},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE allergies SET code = 'changed' WHERE id = :id"),
                    {"id": allergy_id},
                )
        with pytest.raises(Exception, match="cannot be deleted|permission denied"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM allergies WHERE id = :id"),
                    {"id": allergy_id},
                )
        provenance = await connection.execute(
            text(
                """
                SELECT subject_type FROM clinical_provenances
                WHERE id = (SELECT provenance_id FROM allergies WHERE id = :id)
                """
            ),
            {"id": allergy_id},
        )
        assert provenance.scalar_one() == "ALLERGY"
        fk = await connection.execute(
            text(
                """
                SELECT delete_rule FROM information_schema.referential_constraints
                WHERE constraint_name = 'fk_allergies_provenance_id'
                """
            )
        )
        assert fk.scalar_one() == "RESTRICT"
        audit = await connection.execute(
            text("SELECT action, metadata::text FROM audit_events WHERE resource_id = :id"),
            {"id": allergy_id},
        )
        rows = list(audit)
        actions = {row[0] for row in rows}
        assert "ALLERGY_CREATED" in actions
        assert "ALLERGY_AMENDED" in actions
        assert "ALLERGY_ENTERED_IN_ERROR" in actions
        assert all("Penicillin" not in (row[1] or "") for row in rows)
        assert all("Anaphylaxis" not in (row[1] or "") for row in rows)
        assert all("373270004" not in (row[1] or "") for row in rows)
        later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'fhir_allergy_intolerances',
                    'fhir_medication_requests','fhir_observations'
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
                  AND table_name IN ('allergies','medications')
                """
            )
        )
        assert present.scalar_one() == 2


@requires_db
async def test_anonymous_merged_and_encounter_allergy_binding(db_client, db_engine) -> None:
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
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(anonymous_id),
    )
    assert blocked.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    allowed = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(anonymous_id, emer.json()["id"]),
    )
    assert allowed.status_code in {200, 201}

    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    foreign_patient = await _active_patient(db_client, other_registrar)
    mismatch = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(
            patient_id, (await _open_encounter(db_client, clinician, other_patient)).json()["id"]
        ),
    )
    assert mismatch.status_code == 409
    foreign = await _open_encounter(db_client, other, foreign_patient)
    cross_org = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id, foreign.json()["id"]),
    )
    assert cross_org.status_code == 404
    unknown_enc = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id, str(uuid4())),
    )
    assert unknown_enc.status_code == 404

    cancelled = await _open_encounter(db_client, clinician, patient_id)
    cancel = await db_client.post(
        f"/api/v1/clinical/encounters/{cancelled.json()['id']}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "CANCELLED"},
    )
    assert cancel.status_code == 200
    blocked_cancelled = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id, cancelled.json()["id"]),
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
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id, erroneous.json()["id"]),
    )
    assert blocked_eie_enc.status_code == 409

    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Alg",
            "family_name": "Source",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B3B"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Alg", family="Survivor", birth="1982-02-02"),
    )
    historical = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(source.json()["id"]),
    )
    assert historical.status_code in {200, 201}
    historical_id = historical.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.3b historical allergy",
            "evidence": merge_evidence("wave2b3b-hist"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/allergies/{historical_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    created = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(source.json()["id"]),
    )
    assert created.json()["patient_identity_id"] == survivor.json()["id"]
    retired = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    rejected = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(retired),
    )
    assert rejected.status_code == 409
    missing = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(str(uuid4())),
    )
    assert missing.status_code == 404


@requires_db
async def test_allergy_concurrency_facility_and_app_dml(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id, severity="MODERATE"),
    )
    allergy_id = created.json()["id"]

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/allergies/{allergy_id}/amend",
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
                WHERE resource_id = :id AND action = 'ALLERGY_AMENDED'
                """
            ),
            {"id": allergy_id},
        )
        assert events.scalar_one() == 1

    other = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id, severity="MILD"),
    )
    other_id = other.json()["id"]

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/allergies/{other_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(void(), void())
    assert sorted([left.status_code, right.status_code]) == [200, 409]

    race = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id),
    )
    race_id = race.json()["id"]

    async def amend_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/allergies/{race_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_amend_body(),
        )

    async def void_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/allergies/{race_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    raced_left, raced_right = await asyncio.gather(amend_race(), void_race())
    codes = {raced_left.status_code, raced_right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status FROM allergies WHERE id = :id"),
            {"id": race_id},
        )
        assert row.scalar_one() == "ENTERED_IN_ERROR"
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ALLERGY_ENTERED_IN_ERROR'
                """
            ),
            {"id": race_id},
        )
        amended_count = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'ALLERGY_AMENDED'
                """
            ),
            {"id": race_id},
        )
        assert eie.scalar_one() == 1
        assert amended_count.scalar_one() in {0, 1}

    in_scope = new_id()
    out_of_scope = new_id()
    async with db_engine.begin() as connection:
        for facility_id, code in ((in_scope, "AIN"), (out_of_scope, "AOUT")):
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
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=_headers(bound, "TREATMENT", str(in_scope)),
    )
    assert allowed.status_code == 200
    denied = await db_client.get(
        f"/api/v1/clinical/allergies/{allergy_id}",
        headers=_headers(bound, "TREATMENT", str(out_of_scope)),
    )
    assert denied.status_code == 403
    assert "Penicillin" not in denied.text

    async with db_engine.connect() as connection:
        provenance = await connection.execute(
            text("SELECT provenance_id FROM allergies WHERE id = :id"),
            {"id": allergy_id},
        )
        provenance_id = provenance.scalar_one()
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="foreign key|fk_allergies_provenance"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO allergies (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, status, clinical_status,
                            verification_status, recorded_at, version, provenance_id
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               category, code_system, code, 'ACTIVE', clinical_status,
                               verification_status, now(), 1, :bad
                        FROM allergies WHERE id = :id
                        """
                    ),
                    {"id": allergy_id, "bad": uuid4()},
                )
        with pytest.raises(Exception, match=PROVENANCE_DELETE_DENIED):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM clinical_provenances WHERE id = :id"),
                    {"id": provenance_id},
                )
        with pytest.raises(Exception, match="invalid allergy status transition"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE allergies SET status = 'ACTIVE' WHERE id = :id"),
                    {"id": allergy_id},
                )

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM allergies WHERE id = :id"),
                        {"id": allergy_id},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE allergies SET code_display = 'Bypass' WHERE id = :id"),
                        {"id": allergy_id},
                    )
    finally:
        await engine.dispose()
