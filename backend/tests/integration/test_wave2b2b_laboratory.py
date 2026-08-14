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

LOINC = "http://loinc.org"
APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


def _lab_order(
    patient_id: str,
    encounter_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "patient_identity_id": patient_id,
        "code": {"system": LOINC, "code": "24323-8", "display": "Comprehensive metabolic panel"},
    }
    if encounter_id is not None:
        payload["encounter_id"] = encounter_id
    return payload


def _glucose(specimen_id: str, value: float = 5.4) -> dict[str, object]:
    return {
        "laboratory_specimen_id": specimen_id,
        "code": {"system": LOINC, "code": "2345-7", "display": "Glucose"},
        "value_type": "NUMERIC",
        "value_numeric": value,
        "unit": "mmol/L",
        "reference_range_low": 3.9,
        "reference_range_high": 5.8,
        "interpretation": "NORMAL",
    }


async def _collect_specimen(db_client, clinician: SeededActor, order_id: str):
    return await db_client.post(
        "/api/v1/clinical/laboratory/specimens",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"laboratory_order_id": order_id, "specimen_type": "BLOOD"},
    )


async def _open_lab_result(
    db_client,
    clinician: SeededActor,
    patient_id: str,
    *,
    encounter_id: str | None = None,
    value: float = 5.4,
):
    order = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id, encounter_id),
    )
    assert order.status_code in {200, 201}
    specimen = await _collect_specimen(db_client, clinician, order.json()["id"])
    assert specimen.status_code in {200, 201}
    result = await db_client.post(
        "/api/v1/clinical/laboratory/results",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_glucose(specimen.json()["id"], value),
    )
    assert result.status_code in {200, 201}
    return order, specimen, result


@requires_db
async def test_laboratory_lifecycle_identity_and_authorization(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]

    invalid = await db_client.post(
        "/api/v1/clinical/laboratory/results",
        headers=clinician.headers(purpose="TREATMENT"),
        json={
            **_glucose(str(uuid4())),
            "value_text": "5.4",
        },
    )
    assert invalid.status_code == 422

    created_order = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id, encounter_id),
    )
    assert created_order.status_code in {200, 201}
    assert created_order.json()["status"] == "REGISTERED"
    order_id = created_order.json()["id"]

    denied = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id),
    )
    assert denied.status_code == 403

    specimen = await _collect_specimen(db_client, clinician, order_id)
    assert specimen.status_code in {200, 201}
    assert specimen.json()["status"] == "COLLECTED"
    progressed = await db_client.get(
        f"/api/v1/clinical/laboratory/orders/{order_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert progressed.json()["status"] == "IN_PROGRESS"
    cancelled_busy = await db_client.post(
        f"/api/v1/clinical/laboratory/orders/{order_id}/cancel",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert cancelled_busy.status_code == 409

    created = await db_client.post(
        "/api/v1/clinical/laboratory/results",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_glucose(specimen.json()["id"]),
    )
    assert created.status_code in {200, 201}
    assert created.json()["status"] == "FINAL"
    assert created.json()["version"] == 1
    result_id = created.json()["id"]

    listed = await db_client.get(
        "/api/v1/clinical/laboratory/results",
        headers=clinician.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert listed.status_code == 200
    assert result_id in {item["id"] for item in listed.json()}

    amended = await db_client.post(
        f"/api/v1/clinical/laboratory/results/{result_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json={
            "value_type": "NUMERIC",
            "value_numeric": 6.1,
            "unit": "mmol/L",
            "reference_range_low": 3.9,
            "reference_range_high": 5.8,
            "interpretation": "ABNORMAL",
        },
    )
    assert amended.status_code == 200
    assert amended.json()["status"] == "AMENDED"
    assert amended.json()["version"] == 2
    assert float(amended.json()["value_numeric"]) == 6.1
    noop = await db_client.post(
        f"/api/v1/clinical/laboratory/results/{result_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json={
            "value_type": "NUMERIC",
            "value_numeric": 6.1,
            "unit": "mmol/L",
            "reference_range_low": 3.9,
            "reference_range_high": 5.8,
            "interpretation": "ABNORMAL",
        },
    )
    assert noop.status_code == 409

    voided = await db_client.post(
        f"/api/v1/clinical/laboratory/results/{result_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    blocked = await db_client.post(
        f"/api/v1/clinical/laboratory/results/{result_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"value_type": "NUMERIC", "value_numeric": 7.0, "unit": "mmol/L"},
    )
    assert blocked.status_code == 409

    idle = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id),
    )
    cancelled = await db_client.post(
        f"/api/v1/clinical/laboratory/orders/{idle.json()['id']}/cancel",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    blocked_specimen = await _collect_specimen(db_client, clinician, idle.json()["id"])
    assert blocked_specimen.status_code == 409

    rejected = await db_client.post(
        f"/api/v1/clinical/laboratory/specimens/{specimen.json()['id']}/reject",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    blocked_result = await db_client.post(
        "/api/v1/clinical/laboratory/results",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_glucose(specimen.json()["id"], 4.2),
    )
    assert blocked_result.status_code == 409

    cross = await db_client.get(
        f"/api/v1/clinical/laboratory/results/{result_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "sqlalchemy" not in cross.text.lower()
    assert "2345-7" not in cross.text
    unknown = await db_client.get(
        f"/api/v1/clinical/laboratory/orders/{uuid4()}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unknown.status_code == 404
    deleted = await db_client.delete(
        f"/api/v1/clinical/laboratory/results/{result_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
    missing_purpose = await db_client.get(
        f"/api/v1/clinical/laboratory/results/{result_id}",
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
                    text("UPDATE laboratory_results SET patient_identity_id = :pid WHERE id = :id"),
                    {"id": result_id, "pid": uuid4()},
                )
        with pytest.raises(Exception, match="cannot be deleted"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM laboratory_orders WHERE id = :id"),
                    {"id": order_id},
                )
        audit = await connection.execute(
            text("SELECT action, metadata::text FROM audit_events WHERE resource_id = :id"),
            {"id": result_id},
        )
        rows = list(audit)
        actions = {row[0] for row in rows}
        assert "LAB_RESULT_CREATED" in actions
        assert "LAB_RESULT_AMENDED" in actions
        assert "LAB_RESULT_ENTERED_IN_ERROR" in actions
        assert all("2345-7" not in (row[1] or "") for row in rows)
        assert all("5.4" not in (row[1] or "") and "6.1" not in (row[1] or "") for row in rows)
        later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'medications','allergies','fhir_observations',
                    'fhir_specimens','fhir_diagnostic_reports'
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
                    'laboratory_orders','laboratory_specimens','laboratory_results'
                  )
                """
            )
        )
        assert present.scalar_one() == 3


@requires_db
async def test_anonymous_merged_and_encounter_laboratory_binding(db_client, db_engine) -> None:
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
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(anonymous_id),
    )
    assert blocked.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    allowed = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(anonymous_id, emer.json()["id"]),
    )
    assert allowed.status_code in {200, 201}

    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    foreign_patient = await _active_patient(db_client, other_registrar)
    mismatch = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(
            patient_id, (await _open_encounter(db_client, clinician, other_patient)).json()["id"]
        ),
    )
    assert mismatch.status_code == 409
    foreign = await _open_encounter(db_client, other, foreign_patient)
    cross_org = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id, foreign.json()["id"]),
    )
    assert cross_org.status_code == 404
    unknown_enc = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id, str(uuid4())),
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
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id, cancelled.json()["id"]),
    )
    assert blocked_cancelled.status_code == 409
    async with db_engine.connect() as connection:
        mutated = await connection.execute(
            text("SELECT status FROM encounters WHERE id = :id"),
            {"id": cancelled.json()["id"]},
        )
        assert mutated.scalar_one() == "CANCELLED"

    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Lab",
            "family_name": "Source",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B2B"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Lab", family="Survivor", birth="1982-02-02"),
    )
    historical = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(source.json()["id"]),
    )
    assert historical.status_code in {200, 201}
    historical_id = historical.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.2b historical laboratory",
            "evidence": merge_evidence("wave2b2b-hist"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/laboratory/orders/{historical_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    created = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(source.json()["id"]),
    )
    assert created.json()["patient_identity_id"] == survivor.json()["id"]
    retired = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    rejected = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(retired),
    )
    assert rejected.status_code == 409
    missing = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(str(uuid4())),
    )
    assert missing.status_code == 404


@requires_db
async def test_laboratory_authz_purpose_idor_and_facility_scope(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    _order, _specimen, created = await _open_lab_result(db_client, clinician, patient_id)
    result_id = created.json()["id"]
    sibling = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(other_patient),
    )
    assert sibling.status_code in {200, 201}

    unauthenticated = await db_client.get(f"/api/v1/clinical/laboratory/results/{result_id}")
    assert unauthenticated.status_code == 401
    invalid_purpose = await db_client.get(
        f"/api/v1/clinical/laboratory/results/{result_id}",
        headers=clinician.headers(purpose="NOT_A_PURPOSE"),
    )
    assert invalid_purpose.status_code == 422
    registrar_read = await db_client.get(
        f"/api/v1/clinical/laboratory/results/{result_id}",
        headers=registrar.headers(purpose="TREATMENT"),
    )
    assert registrar_read.status_code == 403
    assert "2345-7" not in registrar_read.text
    assert "mmol/L" not in registrar_read.text
    same_org_other_patient = await db_client.get(
        f"/api/v1/clinical/laboratory/orders/{sibling.json()['id']}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert same_org_other_patient.status_code == 200
    cross_org = await db_client.get(
        f"/api/v1/clinical/laboratory/results/{result_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross_org.status_code == 404
    assert "sqlalchemy" not in cross_org.text.lower()
    malformed = await db_client.get(
        "/api/v1/clinical/laboratory/results/not-a-uuid",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert malformed.status_code == 422
    unauthorized_list = await db_client.get(
        "/api/v1/clinical/laboratory/orders",
        headers=registrar.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert unauthorized_list.status_code == 403

    in_scope = new_id()
    out_of_scope = new_id()
    async with db_engine.begin() as connection:
        for facility_id, code in ((in_scope, "LIN2"), (out_of_scope, "LOUT2")):
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
        f"/api/v1/clinical/laboratory/results/{result_id}",
        headers=_headers(bound, "TREATMENT", str(in_scope)),
    )
    assert allowed.status_code == 200
    denied = await db_client.get(
        f"/api/v1/clinical/laboratory/results/{result_id}",
        headers=_headers(bound, "TREATMENT", str(out_of_scope)),
    )
    assert denied.status_code == 403
    assert "2345-7" not in denied.text


@requires_db
async def test_laboratory_concurrency_provenance_and_app_dml(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    _order, _specimen, created = await _open_lab_result(db_client, clinician, patient_id, value=5.0)
    result_id = created.json()["id"]
    organization_id = clinician.organization_id

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/laboratory/results/{result_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json={"value_type": "NUMERIC", "value_numeric": 6.0, "unit": "mmol/L"},
        )

    first, second = await asyncio.gather(amend(), amend())
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'LAB_RESULT_AMENDED'
                """
            ),
            {"id": result_id},
        )
        assert events.scalar_one() == 1

    other_order, _other_specimen, other = await _open_lab_result(
        db_client, clinician, patient_id, value=4.8
    )
    other_id = other.json()["id"]

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/laboratory/results/{other_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(void(), void())
    assert sorted([left.status_code, right.status_code]) == [200, 409]

    race_order, _race_specimen, race = await _open_lab_result(
        db_client, clinician, patient_id, value=4.4
    )
    race_id = race.json()["id"]

    async def race_amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/laboratory/results/{race_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json={"value_type": "NUMERIC", "value_numeric": 8.0, "unit": "mmol/L"},
        )

    async def race_void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/laboratory/results/{race_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    raced_left, raced_right = await asyncio.gather(race_amend(), race_void())
    codes = {raced_left.status_code, raced_right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status, version FROM laboratory_results WHERE id = :id"),
            {"id": race_id},
        )
        status, version = row.one()
        assert status == "ENTERED_IN_ERROR"
        assert version in {1, 2}
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'LAB_RESULT_ENTERED_IN_ERROR'
                """
            ),
            {"id": race_id},
        )
        assert eie.scalar_one() == 1
        provenance = await connection.execute(
            text(
                """
                SELECT provenance_id, subject_type
                FROM laboratory_results r
                JOIN clinical_provenances p ON p.id = r.provenance_id
                WHERE r.id = :id
                """
            ),
            {"id": result_id},
        )
        provenance_id, subject_type = provenance.one()
        rule = await connection.execute(
            text(
                """
                SELECT rc.delete_rule
                FROM information_schema.referential_constraints rc
                WHERE rc.constraint_name = 'fk_laboratory_results_provenance_id'
                """
            )
        )
        delete_rule = rule.scalar_one()
    assert provenance_id is not None
    assert subject_type == "LABORATORY_RESULT"
    assert delete_rule == "RESTRICT"

    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="foreign key|fk_laboratory_results_provenance"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO laboratory_results (
                            id, laboratory_order_id, laboratory_specimen_id,
                            patient_identity_id, organization_id, code_system, code,
                            status, value_type, value_numeric, unit, recorded_at,
                            version, provenance_id
                        ) VALUES (
                            :id, :order_id, :specimen_id, :patient_id, :organization_id,
                            'http://loinc.org', '2345-7', 'FINAL', 'NUMERIC', 5.4, 'mmol/L',
                            now(), 1, :bad
                        )
                        """
                    ),
                    {
                        "id": uuid4(),
                        "order_id": other_order.json()["id"],
                        "specimen_id": _other_specimen.json()["id"],
                        "patient_id": patient_id,
                        "organization_id": organization_id,
                        "bad": uuid4(),
                    },
                )
        with pytest.raises(
            Exception, match="insert-only|foreign key|fk_laboratory_results_provenance"
        ):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM clinical_provenances WHERE id = :id"),
                    {"id": provenance_id},
                )

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM laboratory_results WHERE id = :id"),
                        {"id": result_id},
                    )
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM laboratory_orders WHERE id = :id"),
                        {"id": race_order.json()["id"]},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            "UPDATE laboratory_results"
                            " SET patient_identity_id = :pid WHERE id = :id"
                        ),
                        {"id": result_id, "pid": uuid4()},
                    )
    finally:
        await engine.dispose()
