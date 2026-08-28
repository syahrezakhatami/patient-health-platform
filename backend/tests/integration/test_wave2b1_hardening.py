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
from tests.integration.test_wave1_mpi import merge_evidence, unique_mrn, unique_nik
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave2b1_condition import _pneumonia
from tests.integration.test_wave15_hardening import _headers

pytestmark = [pytest.mark.integration]

APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


@requires_db
async def test_concurrent_identical_status_update_is_serialized(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    condition_id = created.json()["id"]

    async def resolve() -> object:
        return await db_client.post(
            f"/api/v1/clinical/conditions/{condition_id}/status",
            headers=clinician.headers(purpose="TREATMENT"),
            json={"clinical_status": "RESOLVED"},
        )

    first, second = await asyncio.gather(resolve(), resolve())
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    noop = await db_client.post(
        f"/api/v1/clinical/conditions/{condition_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"clinical_status": "RESOLVED"},
    )
    assert noop.status_code == 409
    async with db_engine.connect() as connection:
        status = await connection.execute(
            text("SELECT clinical_status FROM conditions WHERE id = :id"),
            {"id": condition_id},
        )
        assert status.scalar_one() == "RESOLVED"
        events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CONDITION_STATUS_CHANGED'
                """
            ),
            {"id": condition_id},
        )
        assert events.scalar_one() == 1


@requires_db
async def test_concurrent_status_update_versus_entered_in_error(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    condition_id = created.json()["id"]

    async def resolve() -> object:
        return await db_client.post(
            f"/api/v1/clinical/conditions/{condition_id}/status",
            headers=clinician.headers(purpose="TREATMENT"),
            json={"clinical_status": "RESOLVED"},
        )

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/conditions/{condition_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(resolve(), void())
    codes = {left.status_code, right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT clinical_status, verification_status FROM conditions WHERE id = :id"),
            {"id": condition_id},
        )
        clinical_status, verification_status = row.one()
        assert clinical_status in {"ACTIVE", "RESOLVED"}
        assert verification_status in {"CONFIRMED", "ENTERED_IN_ERROR"}
        if verification_status == "CONFIRMED":
            assert clinical_status == "RESOLVED"
        count = await connection.execute(
            text("SELECT count(*) FROM conditions WHERE id = :id"),
            {"id": condition_id},
        )
        assert count.scalar_one() == 1


@requires_db
async def test_concurrent_create_same_patient(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)

    async def create() -> object:
        return await db_client.post(
            "/api/v1/clinical/conditions",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_pneumonia(patient_id),
        )

    first, second = await asyncio.gather(create(), create())
    assert first.status_code in {200, 201}
    assert second.status_code in {200, 201}
    assert first.json()["id"] != second.json()["id"]
    async with db_engine.connect() as connection:
        count = await connection.execute(
            text("SELECT count(*) FROM conditions WHERE patient_identity_id = :id"),
            {"id": patient_id},
        )
        assert count.scalar_one() == 2


@requires_db
async def test_concurrent_create_after_identity_merge(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Race",
            "family_name": "Source",
            "birth_date": "1979-03-03",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B1C"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Race",
            "family_name": "Survivor",
            "birth_date": "1979-03-03",
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": "NIK",
                    "identifier_value": unique_nik(),
                }
            ],
        },
    )
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.1 concurrent merge writes",
            "evidence": merge_evidence("wave2b1-conc"),
        },
    )
    assert merged.status_code in {200, 201}

    async def create() -> object:
        return await db_client.post(
            "/api/v1/clinical/conditions",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_pneumonia(source.json()["id"]),
        )

    first, second = await asyncio.gather(create(), create())
    assert first.status_code in {200, 201}
    assert second.status_code in {200, 201}
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["patient_identity_id"] == survivor.json()["id"]
    assert second.json()["patient_identity_id"] == survivor.json()["id"]
    async with db_engine.connect() as connection:
        bound = await connection.execute(
            text(
                """
                SELECT DISTINCT patient_identity_id::text FROM conditions
                WHERE id IN (:first, :second)
                """
            ),
            {"first": first.json()["id"], "second": second.json()["id"]},
        )
        assert bound.scalars().all() == [survivor.json()["id"]]


@requires_db
async def test_historical_condition_not_rewritten_after_merge(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Hist",
            "family_name": "Source",
            "birth_date": "1981-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B1H"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Hist",
            "family_name": "Survivor",
            "birth_date": "1981-02-02",
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": "NIK",
                    "identifier_value": unique_nik(),
                }
            ],
        },
    )
    created = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(source.json()["id"]),
    )
    assert created.status_code in {200, 201}
    condition_id = created.json()["id"]
    assert created.json()["patient_identity_id"] == source.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.1 historical condition",
            "evidence": merge_evidence("wave2b1-hist"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/conditions/{condition_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.status_code == 200
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    async with db_engine.connect() as connection:
        stored = await connection.execute(
            text("SELECT patient_identity_id FROM conditions WHERE id = :id"),
            {"id": condition_id},
        )
        assert str(stored.scalar_one()) == source.json()["id"]


@requires_db
async def test_encounter_diagnosis_boundaries(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    other_registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=other.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    foreign_patient = await _active_patient(db_client, other_registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    other_encounter = (await _open_encounter(db_client, clinician, other_patient)).json()["id"]
    foreign = await _open_encounter(db_client, other, foreign_patient)
    unknown = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id, str(uuid4())),
    )
    assert unknown.status_code == 404
    assert "sqlalchemy" not in unknown.text.lower()
    mismatch = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id, other_encounter),
    )
    assert mismatch.status_code == 409
    assert foreign.status_code in {200, 201}
    cross_org = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id, foreign.json()["id"]),
    )
    assert cross_org.status_code == 404
    assert "sqlalchemy" not in cross_org.text.lower()
    cancelled = await db_client.post(
        f"/api/v1/clinical/encounters/{encounter_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "CANCELLED"},
    )
    assert cancelled.status_code == 200
    blocked = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id, encounter_id),
    )
    assert blocked.status_code == 409


@requires_db
async def test_condition_authz_purpose_idor_and_delete(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    condition_id = created.json()["id"]
    unauthenticated = await db_client.get(f"/api/v1/clinical/conditions/{condition_id}")
    assert unauthenticated.status_code == 401
    invalid_purpose = await db_client.get(
        f"/api/v1/clinical/conditions/{condition_id}",
        headers=clinician.headers(purpose="NOT_A_PURPOSE"),
    )
    assert invalid_purpose.status_code == 422
    emergency_allowed = await db_client.get(
        f"/api/v1/clinical/conditions/{condition_id}",
        headers=clinician.headers(purpose="EMERGENCY"),
    )
    assert emergency_allowed.status_code == 200
    registrar_read = await db_client.get(
        f"/api/v1/clinical/conditions/{condition_id}",
        headers=registrar.headers(purpose="TREATMENT"),
    )
    assert registrar_read.status_code == 403
    registrar_emergency = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=registrar.headers(purpose="EMERGENCY"),
        json=_pneumonia(patient_id),
    )
    assert registrar_emergency.status_code == 403
    deleted = await db_client.delete(
        f"/api/v1/clinical/conditions/{condition_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
    malformed = await db_client.get(
        "/api/v1/clinical/conditions/not-a-uuid",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert malformed.status_code == 422

    in_scope = new_id()
    out_of_scope = new_id()
    async with db_engine.begin() as connection:
        for facility_id, code in ((in_scope, "CIN2"), (out_of_scope, "COUT2")):
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
        f"/api/v1/clinical/conditions/{condition_id}",
        headers=_headers(bound, "TREATMENT", str(in_scope)),
    )
    assert allowed.status_code == 200
    denied = await db_client.get(
        f"/api/v1/clinical/conditions/{condition_id}",
        headers=_headers(bound, "TREATMENT", str(out_of_scope)),
    )
    assert denied.status_code == 403

    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE conditions SET patient_identity_id = :pid WHERE id = :id"),
                    {"id": condition_id, "pid": uuid4()},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE conditions SET category = 'ENCOUNTER_DIAGNOSIS' WHERE id = :id"),
                    {"id": condition_id},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE conditions SET code_system = 'http://example.org' WHERE id = :id"),
                    {"id": condition_id},
                )


@requires_db
async def test_app_dml_cannot_delete_conditions(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    condition_id = created.json()["id"]
    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM conditions WHERE id = :id"), {"id": condition_id}
                    )
    finally:
        await engine.dispose()
    still = await db_client.get(
        f"/api/v1/clinical/conditions/{condition_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert still.status_code == 200


@requires_db
async def test_condition_provenance_fk_rejects_orphans_and_restricts_delete(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    assert created.status_code in {200, 201}
    condition_id = created.json()["id"]
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT organization_id, provenance_id FROM conditions WHERE id = :id"),
            {"id": condition_id},
        )
        organization_id, provenance_id = row.one()
    assert provenance_id is not None
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="foreign key|fk_conditions_provenance"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO conditions (
                            id, patient_identity_id, organization_id, category,
                            code_system, code, clinical_status, verification_status,
                            recorded_at, provenance_id
                        ) VALUES (
                            :id, :patient_id, :organization_id, 'PROBLEM_LIST_ITEM',
                            'http://example.org', 'X99', 'ACTIVE', 'CONFIRMED',
                            now(), :bad
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
    async with db_engine.connect() as connection:
        rule = await connection.execute(
            text(
                """
                SELECT rc.delete_rule
                FROM information_schema.referential_constraints rc
                WHERE rc.constraint_name = 'fk_conditions_provenance_id'
                """
            )
        )
        assert rule.scalar_one() == "RESTRICT"
    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="foreign key|fk_conditions_provenance"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            """
                            INSERT INTO conditions (
                                id, patient_identity_id, organization_id, category,
                                code_system, code, clinical_status, verification_status,
                                recorded_at, provenance_id
                            ) VALUES (
                                :id, :patient_id, :organization_id, 'PROBLEM_LIST_ITEM',
                                'http://example.org', 'X98', 'ACTIVE', 'CONFIRMED',
                                now(), :bad
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


@requires_db
async def test_condition_historical_facts_are_sql_immutable(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json={
            **_pneumonia(patient_id),
            "onset_at": "2020-01-15T00:00:00Z",
            "abatement_at": "2020-02-01T00:00:00Z",
        },
    )
    assert created.status_code in {200, 201}
    condition_id = created.json()["id"]
    assert created.json()["onset_at"] is not None
    assert created.json()["recorded_at"] is not None
    async with db_engine.connect() as connection:
        for sql in (
            "UPDATE conditions SET onset_at = now() WHERE id = :id",
            "UPDATE conditions SET abatement_at = now() WHERE id = :id",
            "UPDATE conditions SET recorded_at = now() WHERE id = :id",
            "UPDATE conditions SET facility_id = :facility WHERE id = :id",
            "UPDATE conditions SET provenance_id = :provenance WHERE id = :id",
        ):
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text(sql),
                        {
                            "id": condition_id,
                            "facility": uuid4(),
                            "provenance": uuid4(),
                        },
                    )
    resolved = await db_client.post(
        f"/api/v1/clinical/conditions/{condition_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"clinical_status": "RESOLVED"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["clinical_status"] == "RESOLVED"
    assert resolved.json()["onset_at"] == created.json()["onset_at"]
    assert resolved.json()["recorded_at"] == created.json()["recorded_at"]
    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE conditions SET recorded_at = now() WHERE id = :id"),
                        {"id": condition_id},
                    )
    finally:
        await engine.dispose()
