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
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave2b2a_observation import _heart_rate
from tests.integration.test_wave15_hardening import _headers

pytestmark = [pytest.mark.integration]

APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


@requires_db
async def test_concurrent_amend_versus_entered_in_error(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_heart_rate(patient_id, value=70),
    )
    observation_id = created.json()["id"]

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/observations/{observation_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json={"value_type": "NUMERIC", "value_numeric": 80, "unit": "beats/min"},
        )

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/observations/{observation_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(amend(), void())
    codes = {left.status_code, right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status, version FROM observations WHERE id = :id"),
            {"id": observation_id},
        )
        status, version = row.one()
        assert status == "ENTERED_IN_ERROR"
        assert version in {1, 2}
        count = await connection.execute(
            text("SELECT count(*) FROM observations WHERE id = :id"),
            {"id": observation_id},
        )
        assert count.scalar_one() == 1
        eie = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'OBSERVATION_ENTERED_IN_ERROR'
                """
            ),
            {"id": observation_id},
        )
        assert eie.scalar_one() == 1
        amended = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'OBSERVATION_AMENDED'
                """
            ),
            {"id": observation_id},
        )
        assert amended.scalar_one() == (1 if version == 2 else 0)


@requires_db
async def test_cancelled_and_entered_in_error_encounters_reject_observations(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    cancelled = await _open_encounter(db_client, clinician, patient_id)
    cancel = await db_client.post(
        f"/api/v1/clinical/encounters/{cancelled.json()['id']}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "CANCELLED"},
    )
    assert cancel.status_code == 200
    blocked_cancelled = await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_heart_rate(patient_id, cancelled.json()["id"]),
    )
    assert blocked_cancelled.status_code == 409

    erroneous = await _open_encounter(db_client, clinician, patient_id)
    void_encounter = await db_client.post(
        f"/api/v1/clinical/encounters/{erroneous.json()['id']}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "ENTERED_IN_ERROR"},
    )
    assert void_encounter.status_code == 200
    blocked_eie = await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_heart_rate(patient_id, erroneous.json()["id"]),
    )
    assert blocked_eie.status_code == 409
    async with db_engine.connect() as connection:
        mutated = await connection.execute(
            text("SELECT status FROM encounters WHERE id = :id"),
            {"id": cancelled.json()["id"]},
        )
        assert mutated.scalar_one() == "CANCELLED"


@requires_db
async def test_observation_authz_purpose_idor_and_facility_scope(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_heart_rate(patient_id),
    )
    observation_id = created.json()["id"]
    sibling = await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_heart_rate(other_patient, value=64),
    )
    assert sibling.status_code in {200, 201}

    unauthenticated = await db_client.get(f"/api/v1/clinical/observations/{observation_id}")
    assert unauthenticated.status_code == 401
    invalid_purpose = await db_client.get(
        f"/api/v1/clinical/observations/{observation_id}",
        headers=clinician.headers(purpose="NOT_A_PURPOSE"),
    )
    assert invalid_purpose.status_code == 422
    registrar_read = await db_client.get(
        f"/api/v1/clinical/observations/{observation_id}",
        headers=registrar.headers(purpose="TREATMENT"),
    )
    assert registrar_read.status_code == 403
    assert "8867-4" not in registrar_read.text
    assert "beats/min" not in registrar_read.text
    same_org_other_patient = await db_client.get(
        f"/api/v1/clinical/observations/{sibling.json()['id']}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert same_org_other_patient.status_code == 200
    cross_org = await db_client.get(
        f"/api/v1/clinical/observations/{observation_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross_org.status_code == 404
    assert "sqlalchemy" not in cross_org.text.lower()
    assert "8867-4" not in cross_org.text
    malformed = await db_client.get(
        "/api/v1/clinical/observations/not-a-uuid",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert malformed.status_code == 422
    unauthorized_list = await db_client.get(
        "/api/v1/clinical/observations",
        headers=registrar.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert unauthorized_list.status_code == 403

    in_scope = new_id()
    out_of_scope = new_id()
    async with db_engine.begin() as connection:
        for facility_id, code in ((in_scope, "OIN2"), (out_of_scope, "OOUT2")):
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
        f"/api/v1/clinical/observations/{observation_id}",
        headers=_headers(bound, "TREATMENT", str(in_scope)),
    )
    assert allowed.status_code == 200
    denied = await db_client.get(
        f"/api/v1/clinical/observations/{observation_id}",
        headers=_headers(bound, "TREATMENT", str(out_of_scope)),
    )
    assert denied.status_code == 403
    assert "8867-4" not in denied.text


@requires_db
async def test_observation_provenance_fk_and_app_dml_immutability(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_heart_rate(patient_id),
    )
    observation_id = created.json()["id"]
    organization_id = clinician.organization_id
    async with db_engine.connect() as connection:
        provenance = await connection.execute(
            text(
                """
                SELECT provenance_id, subject_type
                FROM observations o
                JOIN clinical_provenances p ON p.id = o.provenance_id
                WHERE o.id = :id
                """
            ),
            {"id": observation_id},
        )
        provenance_id, subject_type = provenance.one()
        rule = await connection.execute(
            text(
                """
                SELECT rc.delete_rule
                FROM information_schema.referential_constraints rc
                WHERE rc.constraint_name = 'fk_observations_provenance_id'
                """
            )
        )
        delete_rule = rule.scalar_one()
    assert provenance_id is not None
    assert subject_type == "OBSERVATION"
    assert delete_rule == "RESTRICT"
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="foreign key|fk_observations_provenance"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO observations (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, status, value_type, value_numeric, unit,
                            recorded_at, version, provenance_id
                        ) VALUES (
                            :id, :patient_id, :organization_id, 'VITAL_SIGNS',
                            'http://loinc.org', '8867-4', 'FINAL', 'NUMERIC', 72, 'beats/min',
                            now(), 1, :bad
                        )
                        """
                    ),
                    {
                        "id": uuid4(),
                        "patient_id": patient_id,
                        "organization_id": organization_id,
                        "bad": uuid4(),
                    },
                )
        with pytest.raises(Exception, match=PROVENANCE_DELETE_DENIED):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM clinical_provenances WHERE id = :id"),
                    {"id": provenance_id},
                )

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE observations SET patient_identity_id = :pid WHERE id = :id"),
                        {"id": observation_id, "pid": uuid4()},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE observations SET category = 'EXAM' WHERE id = :id"),
                        {"id": observation_id},
                    )
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM observations WHERE id = :id"),
                        {"id": observation_id},
                    )
            with pytest.raises(Exception, match="foreign key|fk_observations_provenance"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            """
                            INSERT INTO observations (
                                id, patient_identity_id, organization_id, category,
                                code_system, code, status, value_type, value_numeric, unit,
                                recorded_at, version, provenance_id
                            ) VALUES (
                                :id, :patient_id, :organization_id, 'VITAL_SIGNS',
                                'http://loinc.org', '8867-4', 'FINAL', 'NUMERIC', 72, 'beats/min',
                                now(), 1, :bad
                            )
                            """
                        ),
                        {
                            "id": uuid4(),
                            "patient_id": patient_id,
                            "organization_id": organization_id,
                            "bad": uuid4(),
                        },
                    )
    finally:
        await engine.dispose()
