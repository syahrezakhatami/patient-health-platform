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
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.test_product_access_tenancy_foundation import _patient_headers
from tests.integration.test_wave1_mpi import unique_nik
from tests.integration.test_wave2a_hardening import _active_patient
from tests.integration.test_wave2b1_condition import _pneumonia
from tests.integration.test_wave2b3b_allergy import _penicillin
from tests.integration.test_wave2b3c_consent import _consent
from tests.integration.test_wave15_hardening import _headers

pytestmark = pytest.mark.integration


async def _insert_facility(engine, organization_id, *, prefix: str) -> object:
    facility_id = new_id()
    async with engine.begin() as connection:
        await connection.execute(
            FacilityModel.__table__.insert().values(
                id=facility_id,
                organization_id=organization_id,
                name=f"{prefix} ward",
                code=f"{prefix}{facility_id.hex[:6].upper()}",
                facility_type=FacilityType.CLINIC_SITE,
                status=FacilityStatus.ACTIVE,
            )
        )
    return facility_id


async def _seed_facility_bound_clinician(engine, organization_id, facility_id) -> SeededActor:
    bound_user = new_id()
    subject = f"user-{bound_user}"
    async with engine.begin() as connection:
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


def _no_leak(response) -> None:
    body = response.text.lower()
    assert "traceback" not in body
    assert "sqlalchemy" not in body
    assert "hospital b" not in body
    assert "foreign ward" not in body


async def _post(
    db_client, actor: SeededActor, path: str, payload, *, facility_id=None, org_id=None
):
    headers = actor.headers(purpose="TREATMENT" if "clinical" in path else "registration")
    if org_id is not None:
        headers["X-Organization-Id"] = str(org_id)
    if facility_id is not None:
        headers["X-Facility-Id"] = str(facility_id)
    return await db_client.post(path, headers=headers, json=payload)


@requires_db
async def test_empty_facility_list_same_org_allowed_foreign_denied(db_client, db_engine) -> None:
    hospital = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    clinic = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital.organization_id
    )
    facility_a1 = await _insert_facility(db_engine, hospital.organization_id, prefix="A1")
    facility_a2 = await _insert_facility(db_engine, hospital.organization_id, prefix="A2")
    facility_b1 = await _insert_facility(db_engine, clinic.organization_id, prefix="B1")
    patient_id = await _active_patient(db_client, registrar)

    for facility_id, expected in ((facility_a1, 201), (facility_a2, 201), (None, 201)):
        created = await _post(
            db_client,
            hospital,
            "/api/v1/clinical/conditions",
            _pneumonia(patient_id),
            facility_id=facility_id,
        )
        assert created.status_code in {200, expected}, created.text
        if facility_id is None:
            assert created.json()["facility_id"] is None
        else:
            assert created.json()["facility_id"] == str(facility_id)
            assert created.json()["organization_id"] == str(hospital.organization_id)

    foreign = await _post(
        db_client,
        hospital,
        "/api/v1/clinical/conditions",
        _pneumonia(patient_id),
        facility_id=facility_b1,
    )
    assert foreign.status_code == 404, foreign.text
    _no_leak(foreign)
    unknown = await _post(
        db_client,
        hospital,
        "/api/v1/clinical/conditions",
        _pneumonia(patient_id),
        facility_id=new_id(),
    )
    assert unknown.status_code == 404, unknown.text


@requires_db
@pytest.mark.parametrize(
    ("path", "purpose", "role", "kind"),
    [
        ("/api/v1/clinical/conditions", "TREATMENT", RoleCode.CLINICIAN, "condition"),
        ("/api/v1/clinical/encounters", "TREATMENT", RoleCode.CLINICIAN, "encounter"),
        ("/api/v1/clinical/allergies", "TREATMENT", RoleCode.CLINICIAN, "allergy"),
        ("/api/v1/clinical/consents", "TREATMENT", RoleCode.CLINICIAN, "consent"),
        ("/api/v1/mpi/identities", "registration", RoleCode.REGISTRAR, "identity"),
    ],
)
async def test_empty_list_foreign_facility_denied_on_writes(
    db_client, db_engine, path, purpose, role, kind
) -> None:
    actor = await seed_actor(db_engine, role_code=role)
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = actor
    if role != RoleCode.REGISTRAR:
        registrar = await seed_actor(
            db_engine, role_code=RoleCode.REGISTRAR, organization_id=actor.organization_id
        )
    facility_b1 = await _insert_facility(db_engine, other.organization_id, prefix="XF")
    patient_id = None if kind == "identity" else await _active_patient(db_client, registrar)
    payload = {
        "condition": lambda: _pneumonia(patient_id),
        "encounter": lambda: {"patient_identity_id": patient_id, "encounter_class": "AMB"},
        "allergy": lambda: _penicillin(patient_id),
        "consent": lambda: _consent(patient_id),
        "identity": lambda: {
            "given_name": "Ada",
            "family_name": "Patient",
            "birth_date": "1991-02-02",
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": "NIK",
                    "identifier_value": unique_nik(),
                }
            ],
        },
    }[kind]()
    headers = actor.headers(purpose=purpose)
    headers["X-Facility-Id"] = str(facility_b1)
    denied = await db_client.post(path, headers=headers, json=payload)
    assert denied.status_code == 404, (kind, denied.status_code, denied.text[:400])
    _no_leak(denied)


@requires_db
async def test_explicit_facility_list_is_not_weakened(db_client, db_engine) -> None:
    hospital = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    clinic = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital.organization_id
    )
    facility_a1 = await _insert_facility(db_engine, hospital.organization_id, prefix="S1")
    facility_a2 = await _insert_facility(db_engine, hospital.organization_id, prefix="S2")
    facility_b1 = await _insert_facility(db_engine, clinic.organization_id, prefix="SB")
    bound = await _seed_facility_bound_clinician(db_engine, hospital.organization_id, facility_a1)
    patient_id = await _active_patient(db_client, registrar)

    allowed = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=_headers(bound, "TREATMENT", str(facility_a1)),
        json=_pneumonia(patient_id),
    )
    assert allowed.status_code in {200, 201}
    assert allowed.json()["facility_id"] == str(facility_a1)

    unlisted = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=_headers(bound, "TREATMENT", str(facility_a2)),
        json=_pneumonia(patient_id),
    )
    assert unlisted.status_code == 403
    _no_leak(unlisted)

    foreign = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=_headers(bound, "TREATMENT", str(facility_b1)),
        json=_pneumonia(patient_id),
    )
    assert foreign.status_code == 403
    _no_leak(foreign)


@requires_db
async def test_org_header_tampering_cannot_expand_facility_authority(db_client, db_engine) -> None:
    hospital = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    clinic = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar_a = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital.organization_id
    )
    registrar_b = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinic.organization_id
    )
    facility_b1 = await _insert_facility(db_engine, clinic.organization_id, prefix="HT")
    patient_a = await _active_patient(db_client, registrar_a)
    patient_b = await _active_patient(db_client, registrar_b)

    org_a_facility_b = await _post(
        db_client,
        hospital,
        "/api/v1/clinical/conditions",
        _pneumonia(patient_a),
        facility_id=facility_b1,
    )
    assert org_a_facility_b.status_code == 404

    headers = hospital.headers(purpose="TREATMENT")
    headers["X-Organization-Id"] = str(clinic.organization_id)
    headers["X-Facility-Id"] = str(facility_b1)
    org_b_header = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=headers,
        json=_pneumonia(patient_b),
    )
    assert org_b_header.status_code in {403, 404}
    _no_leak(org_b_header)


@requires_db
async def test_platform_admin_cannot_use_facility_header_for_clinical(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    facility_a = await _insert_facility(db_engine, clinician.organization_id, prefix="PA")
    clinic = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    facility_b = await _insert_facility(db_engine, clinic.organization_id, prefix="PB")
    patient_id = await _active_patient(db_client, registrar)
    for facility_id in (facility_a, facility_b, None):
        headers = platform.headers(purpose="TREATMENT")
        headers["X-Organization-Id"] = str(clinician.organization_id)
        if facility_id is not None:
            headers["X-Facility-Id"] = str(facility_id)
        denied = await db_client.post(
            "/api/v1/clinical/conditions",
            headers=headers,
            json=_pneumonia(patient_id),
        )
        assert denied.status_code == 403, denied.text
        _no_leak(denied)


@requires_db
async def test_patient_cannot_exploit_org_or_facility_context(db_client, db_engine) -> None:
    registrar_a = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    registrar_b = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    facility_b = await _insert_facility(db_engine, registrar_b.organization_id, prefix="PT")
    patient_id = await _active_patient(db_client, registrar_a)
    subject = f"patient-{uuid4()}"
    token = mint_token(sub=subject, aud="php-patient")
    headers = _patient_headers(token, registrar_a.organization_id)
    bound = await db_client.post(
        "/api/v1/patient/accounts",
        headers=headers,
        json={"patient_identity_id": patient_id},
    )
    assert bound.status_code in {200, 201}
    own = await db_client.get("/api/v1/patient/me", headers=headers)
    assert own.status_code == 200
    ignored_facility = dict(headers)
    ignored_facility["X-Facility-Id"] = str(facility_b)
    still_own = await db_client.get("/api/v1/patient/me", headers=ignored_facility)
    assert still_own.status_code == 200

    tampered = _patient_headers(token, registrar_b.organization_id)
    tampered["X-Facility-Id"] = str(facility_b)
    me = await db_client.get("/api/v1/patient/me", headers=tampered)
    assert me.status_code in {200, 404}
    if me.status_code == 200:
        assert me.json()["canonical_patient_identity_id"] == patient_id
    _no_leak(me)
    patient_b = await _active_patient(db_client, registrar_b)
    record = await db_client.get(
        "/api/v1/patient/record-access",
        headers=tampered,
        params={"patient_identity_id": patient_id},
    )
    assert record.status_code == 404
    _no_leak(record)
    foreign_record = await db_client.get(
        "/api/v1/patient/record-access",
        headers=tampered,
        params={"patient_identity_id": patient_b},
    )
    assert foreign_record.status_code == 404
    _no_leak(foreign_record)

    clinical = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=tampered,
        json=_pneumonia(patient_id),
    )
    assert clinical.status_code == 401


@requires_db
async def test_schema_does_not_composite_enforce_facility_org(db_engine) -> None:
    async with db_engine.connect() as connection:
        defs = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT pg_get_constraintdef(oid)
                    FROM pg_constraint
                    WHERE contype = 'f'
                      AND conrelid = 'conditions'::regclass
                    """
                    )
                )
            )
            .scalars()
            .all()
        )
    org_only = any("organization_id" in item and "facility_id" not in item for item in defs)
    facility_only = any("facility_id" in item and "organization_id" not in item for item in defs)
    composite = any("organization_id" in item and "facility_id" in item for item in defs)
    assert org_only
    assert facility_only
    assert not composite


@requires_db
async def test_iam_membership_foreign_facility_is_concealed(db_client, db_engine) -> None:
    admin = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    other = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    target = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=admin.organization_id
    )
    facility_b = await _insert_facility(db_engine, other.organization_id, prefix="IM")
    denied = await db_client.post(
        "/api/v1/iam/memberships",
        headers=admin.headers(purpose="ADMINISTRATION"),
        json={
            "user_id": str(target.user_id),
            "organization_id": str(admin.organization_id),
            "facility_id": str(facility_b),
            "role_code": RoleCode.CLINICIAN,
        },
    )
    assert denied.status_code == 404, denied.text
    _no_leak(denied)
