from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.mpi.domain.enums import IdentifierType
from sqlalchemy import text
from tests.conftest import mint_token
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_wave1_mpi import merge_evidence, unique_nik

pytestmark = pytest.mark.integration


def _identity_payload(
    nik: str, *, given: str = "Ada", family: str = "Patient"
) -> dict[str, object]:
    return {
        "given_name": given,
        "family_name": family,
        "birth_date": "1991-02-02",
        "identifiers": [
            {
                "identifier_system": "id.nik",
                "identifier_type": IdentifierType.NIK,
                "identifier_value": nik,
            }
        ],
    }


def _patient_headers(
    token: str, organization_id, *, purpose: str = "PATIENT_ACCESS"
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Organization-Id": str(organization_id),
        "X-Purpose": purpose,
    }


@requires_db
async def test_platform_admin_clinical_and_mpi_are_forbidden(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    assert created.status_code in {200, 201}
    patient_id = created.json()["id"]
    clinical = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=platform.headers(purpose="TREATMENT"),
        json={
            "patient_identity_id": patient_id,
            "category": "PROBLEM_LIST_ITEM",
            "code": {"system": "http://snomed.info/sct", "code": "38341003"},
        },
    )
    assert clinical.status_code == 403
    mpi_read = await db_client.get(
        f"/api/v1/mpi/identities/{patient_id}",
        headers=platform.headers(purpose="ADMINISTRATION"),
    )
    assert mpi_read.status_code == 403
    clinician_ok = await db_client.get(
        f"/api/v1/mpi/identities/{patient_id}",
        headers=registrar.headers(),
    )
    assert clinician_ok.status_code == 200


@requires_db
async def test_staff_cross_tenant_remains_denied(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    clinic_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar_a = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_a.organization_id
    )
    identity = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar_a.headers(),
        json=_identity_payload(unique_nik()),
    )
    patient_id = identity.json()["id"]
    cross = await db_client.get(
        f"/api/v1/mpi/identities/{patient_id}",
        headers=clinic_b.headers(),
    )
    assert cross.status_code == 404


@requires_db
async def test_patient_account_binding_and_self_access(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    identity = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    assert identity.status_code in {200, 201}
    patient_id = identity.json()["id"]
    subject = f"patient-{uuid4()}"
    token = mint_token(sub=subject, aud="php-patient")
    headers = _patient_headers(token, registrar.organization_id)
    bound = await db_client.post(
        "/api/v1/patient/accounts",
        headers=headers,
        json={"patient_identity_id": patient_id},
    )
    assert bound.status_code in {200, 201}
    assert bound.json()["patient_identity_id"] == patient_id
    assert "nik" not in bound.text.lower()
    me = await db_client.get("/api/v1/patient/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["canonical_patient_identity_id"] == patient_id
    spoof = mint_token(
        sub=subject,
        aud="php-patient",
        extra={"patient_identity_id": str(uuid4())},
    )
    spoofed = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(spoof, registrar.organization_id),
    )
    assert spoofed.status_code == 200
    assert spoofed.json()["canonical_patient_identity_id"] == patient_id
    access = await db_client.get(
        "/api/v1/patient/record-access",
        headers=headers,
        params={"patient_identity_id": patient_id},
    )
    assert access.status_code == 200
    assert patient_id in access.json()["cluster_identity_ids"]


@requires_db
async def test_patient_binding_rejects_duplicates_anonymous_retired_unknown(
    db_client, db_engine
) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    identity = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    patient_id = identity.json()["id"]
    first = mint_token(sub=f"patient-{uuid4()}", aud="php-patient")
    created = await db_client.post(
        "/api/v1/patient/accounts",
        headers=_patient_headers(first, registrar.organization_id),
        json={"patient_identity_id": patient_id},
    )
    assert created.status_code in {200, 201}
    second = mint_token(sub=f"patient-{uuid4()}", aud="php-patient")
    duplicate_identity = await db_client.post(
        "/api/v1/patient/accounts",
        headers=_patient_headers(second, registrar.organization_id),
        json={"patient_identity_id": patient_id},
    )
    assert duplicate_identity.status_code == 409
    duplicate_subject = await db_client.post(
        "/api/v1/patient/accounts",
        headers=_patient_headers(first, registrar.organization_id),
        json={"patient_identity_id": patient_id},
    )
    assert duplicate_subject.status_code == 409
    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=registrar.headers(purpose="EMERGENCY"),
        json={},
    )
    anon_bind = await db_client.post(
        "/api/v1/patient/accounts",
        headers=_patient_headers(
            mint_token(sub=f"patient-{uuid4()}", aud="php-patient"), registrar.organization_id
        ),
        json={"patient_identity_id": anonymous.json()["id"]},
    )
    assert anon_bind.status_code == 409
    unknown = await db_client.post(
        "/api/v1/patient/accounts",
        headers=_patient_headers(
            mint_token(sub=f"patient-{uuid4()}", aud="php-patient"), registrar.organization_id
        ),
        json={"patient_identity_id": str(uuid4())},
    )
    assert unknown.status_code == 404
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": patient_id},
        )
    retired_bind = await db_client.post(
        "/api/v1/patient/accounts",
        headers=_patient_headers(
            mint_token(sub=f"patient-{uuid4()}", aud="php-patient"), registrar.organization_id
        ),
        json={"patient_identity_id": patient_id},
    )
    assert retired_bind.status_code == 409


@requires_db
async def test_patient_cannot_access_other_patient_or_wrong_org(db_client, db_engine) -> None:
    registrar_a = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    registrar_b = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    identity_a = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar_a.headers(),
        json=_identity_payload(unique_nik(), given="Pat"),
    )
    identity_b = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar_b.headers(),
        json=_identity_payload(unique_nik(), given="Other"),
    )
    token = mint_token(sub=f"patient-{uuid4()}", aud="php-patient")
    headers = _patient_headers(token, registrar_a.organization_id)
    bound = await db_client.post(
        "/api/v1/patient/accounts",
        headers=headers,
        json={"patient_identity_id": identity_a.json()["id"]},
    )
    assert bound.status_code in {200, 201}
    other = await db_client.get(
        "/api/v1/patient/record-access",
        headers=headers,
        params={"patient_identity_id": identity_b.json()["id"]},
    )
    assert other.status_code == 404
    guess = await db_client.get(
        "/api/v1/patient/record-access",
        headers=headers,
        params={"patient_identity_id": str(uuid4())},
    )
    assert guess.status_code == 404
    assert identity_b.json()["id"] not in guess.text
    wrong_org = await db_client.get(
        "/api/v1/patient/record-access",
        headers=_patient_headers(token, registrar_b.organization_id),
        params={"patient_identity_id": identity_a.json()["id"]},
    )
    assert wrong_org.status_code == 404


@requires_db
async def test_patient_purpose_and_token_audience_boundaries(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    clinician = await seed_actor(
        db_engine, role_code=RoleCode.CLINICIAN, organization_id=registrar.organization_id
    )
    identity = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    patient_id = identity.json()["id"]
    subject = f"patient-{uuid4()}"
    patient_token = mint_token(sub=subject, aud="php-patient")
    headers = _patient_headers(patient_token, registrar.organization_id)
    bound = await db_client.post(
        "/api/v1/patient/accounts",
        headers=headers,
        json={"patient_identity_id": patient_id},
    )
    assert bound.status_code in {200, 201}
    missing = await db_client.get(
        "/api/v1/patient/me",
        headers={
            "Authorization": f"Bearer {patient_token}",
            "X-Organization-Id": str(registrar.organization_id),
        },
    )
    assert missing.status_code == 422
    unknown_purpose = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(patient_token, registrar.organization_id, purpose="NOT_A_PURPOSE"),
    )
    assert unknown_purpose.status_code == 422
    wrong_purpose = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(patient_token, registrar.organization_id, purpose="TREATMENT"),
    )
    assert wrong_purpose.status_code == 403
    staff_on_patient = await db_client.get(
        "/api/v1/patient/me",
        headers=clinician.headers(purpose="PATIENT_ACCESS"),
    )
    assert staff_on_patient.status_code == 401
    patient_on_clinical = await db_client.get(
        f"/api/v1/clinical/conditions/{uuid4()}",
        headers=headers,
    )
    assert patient_on_clinical.status_code == 401
    platform_token = mint_token(sub=clinician.subject, aud="php-platform")
    platform_on_patient = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(platform_token, registrar.organization_id),
    )
    assert platform_on_patient.status_code == 401
    platform_on_clinical = await db_client.post(
        "/api/v1/clinical/conditions",
        headers={
            "Authorization": f"Bearer {platform_token}",
            "X-Organization-Id": str(registrar.organization_id),
            "X-Purpose": "TREATMENT",
        },
        json={
            "patient_identity_id": patient_id,
            "category": "PROBLEM_LIST_ITEM",
            "code": {"system": "http://snomed.info/sct", "code": "38341003"},
        },
    )
    assert platform_on_clinical.status_code == 401


@requires_db
async def test_merged_identity_rebinds_patient_account(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=registrar.organization_id
    )
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json={
            "given_name": "Source",
            "family_name": "Patient",
            "birth_date": "1991-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": IdentifierType.MRN,
                    "identifier_value": f"MRN-{uuid4().hex[:10].upper()}",
                }
            ],
        },
    )
    target = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik(), given="Target"),
    )
    source_id = source.json()["id"]
    target_id = target.json()["id"]
    token = mint_token(sub=f"patient-{uuid4()}", aud="php-patient")
    headers = _patient_headers(token, registrar.organization_id)
    bound = await db_client.post(
        "/api/v1/patient/accounts",
        headers=headers,
        json={"patient_identity_id": source_id},
    )
    assert bound.status_code in {200, 201}
    merge = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source_id,
            "target_identity_id": target_id,
            "reason": "Duplicate registration confirmed by registrar",
            "evidence": merge_evidence("PAT-ACCESS-1"),
            "idempotency_key": f"merge-{source_id}",
        },
    )
    assert merge.status_code in {200, 201}
    me = await db_client.get("/api/v1/patient/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["canonical_patient_identity_id"] == target_id
    merged_bind = await db_client.post(
        "/api/v1/patient/accounts",
        headers=_patient_headers(
            mint_token(sub=f"patient-{uuid4()}", aud="php-patient"),
            registrar.organization_id,
        ),
        json={"patient_identity_id": source_id},
    )
    assert merged_bind.status_code == 409
    historical = await db_client.get(
        "/api/v1/patient/record-access",
        headers=headers,
        params={"patient_identity_id": source_id},
    )
    assert historical.status_code == 200
    assert source_id in historical.json()["cluster_identity_ids"]


@requires_db
async def test_platform_admin_cannot_assign_clinician(db_client, db_engine) -> None:
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    org_admin = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    target = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=org_admin.organization_id
    )
    denied = await db_client.post(
        "/api/v1/iam/memberships",
        headers=platform.headers(purpose="ADMINISTRATION"),
        json={
            "user_id": str(target.user_id),
            "organization_id": str(org_admin.organization_id),
            "role_code": RoleCode.CLINICIAN,
        },
    )
    assert denied.status_code == 403
    allowed = await db_client.post(
        "/api/v1/iam/memberships",
        headers=platform.headers(purpose="ADMINISTRATION"),
        json={
            "user_id": str(target.user_id),
            "organization_id": str(org_admin.organization_id),
            "role_code": RoleCode.ORG_ADMIN,
        },
    )
    assert allowed.status_code in {200, 201}


@requires_db
async def test_patient_accounts_schema_and_catalog(db_engine) -> None:
    async with db_engine.connect() as connection:
        columns = await connection.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'patient_accounts'
                """
            )
        )
        names = {row[0] for row in columns}
        assert names >= {"id", "subject", "patient_identity_id", "status"}
        assert "nik" not in names
        assert "bpjs" not in names
        fk = await connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid = 'patient_accounts'::regclass AND contype = 'f'
                """
            )
        )
        defs = " ".join(row[0] for row in fk)
        assert "patient_identities" in defs
        assert "ON DELETE RESTRICT" in defs.upper().replace("  ", " ") or "RESTRICT" in defs
        perms = await connection.execute(
            text("SELECT code FROM permissions WHERE code LIKE 'patient.%' ORDER BY code")
        )
        assert [row[0] for row in perms] == ["patient.account.read", "patient.record.read"]
        leftover = await connection.execute(
            text(
                """
                SELECT p.code FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE r.code = 'PLATFORM_ADMIN'
                  AND (p.code LIKE 'clinical.%' OR p.code LIKE 'mpi.%')
                """
            )
        )
        assert leftover.all() == []
