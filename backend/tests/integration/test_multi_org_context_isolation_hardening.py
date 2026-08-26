import asyncio
import hashlib
import inspect
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from app.api.v1.deps import get_principal
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.product_access_pdp import ProductAccessPDP
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.iam.domain.enums import MembershipStatus
from app.modules.iam.infrastructure.models import OrganizationMembershipModel, RoleModel
from app.modules.iam.infrastructure.repositories import IamRepository
from app.shared.types.ids import new_id
from sqlalchemy import select, update
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.test_product_access_multi_org_isolation import (
    _add_facility,
    _add_membership,
    _as_actor,
    _bind_membership_facility,
    _facility_payload,
    _staff_headers,
)
from tests.integration.test_wave1_mpi import merge_evidence, unique_nik
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave2b1_condition import _pneumonia

pytestmark = pytest.mark.integration

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
WAVE1_SHA256 = "f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd"
PRODUCT_ACCESS_SHA256 = "65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc"


def test_frozen_pdps_and_no_principal_cache() -> None:
    wave1 = APP_ROOT / "modules" / "authorization" / "application" / "wave1_pdp.py"
    product = APP_ROOT / "modules" / "authorization" / "application" / "product_access_pdp.py"
    assert hashlib.sha256(wave1.read_bytes()).hexdigest() == WAVE1_SHA256
    assert hashlib.sha256(product.read_bytes()).hexdigest() == PRODUCT_ACCESS_SHA256
    holders = [
        str(path.relative_to(APP_ROOT))
        for path in APP_ROOT.rglob("*.py")
        if "Wave1PolicyPDP()" in path.read_text(encoding="utf-8")
    ]
    assert holders == ["modules/authorization/application/product_access_pdp.py"]
    assert "for_organization" not in inspect.getsource(ProductAccessPDP)
    assert "for_organization" not in inspect.getsource(Wave1PolicyPDP)
    repo_src = inspect.getsource(IamRepository)
    assert "lru_cache" not in repo_src
    assert "@cache" not in repo_src
    deps_src = (APP_ROOT / "api" / "v1" / "deps.py").read_text(encoding="utf-8")
    assert "ContextVar" not in deps_src
    authorize_src = Path(inspect.getfile(authorize)).read_text(encoding="utf-8")
    assert "load_principal" in inspect.getsource(get_principal)
    assert "for_organization" in inspect.getsource(get_principal)
    assert "for_organization" in authorize_src


async def _add_platform_membership(db_engine, user_id: UUID) -> None:
    async with db_engine.begin() as connection:
        role_id = (
            await connection.execute(
                select(RoleModel.id).where(RoleModel.code == RoleCode.PLATFORM_ADMIN)
            )
        ).scalar_one()
        await connection.execute(
            OrganizationMembershipModel.__table__.insert().values(
                id=new_id(),
                user_id=user_id,
                organization_id=None,
                facility_id=None,
                role_id=role_id,
                status=MembershipStatus.ACTIVE,
            )
        )


async def _revoke_membership(db_engine, user_id: UUID, organization_id: UUID) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(
            update(OrganizationMembershipModel)
            .where(
                OrganizationMembershipModel.user_id == user_id,
                OrganizationMembershipModel.organization_id == organization_id,
            )
            .values(status=MembershipStatus.REVOKED)
        )


def _auth_only(actor: SeededActor, purpose: str = "ADMINISTRATION") -> dict[str, str]:
    return {"Authorization": f"Bearer {actor.token}", "X-Purpose": purpose}


@requires_db
async def test_header_path_mismatch_and_missing_header(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.CLINICIAN,
    )
    actor = _as_actor(hospital_a)
    mismatch_a_on_b = await db_client.post(
        f"/api/v1/organizations/{hospital_b.organization_id}/facilities",
        headers=_staff_headers(actor, hospital_a.organization_id, "ADMINISTRATION"),
        json=_facility_payload("Mismatch B"),
    )
    mismatch_b_on_a = await db_client.post(
        f"/api/v1/organizations/{hospital_a.organization_id}/facilities",
        headers=_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
        json=_facility_payload("Mismatch A"),
    )
    no_header_b = await db_client.post(
        f"/api/v1/organizations/{hospital_b.organization_id}/facilities",
        headers=_auth_only(actor),
        json=_facility_payload("No header B"),
    )
    no_header_a = await db_client.post(
        f"/api/v1/organizations/{hospital_a.organization_id}/facilities",
        headers=_auth_only(actor),
        json=_facility_payload("No header A"),
    )
    clinical_no_header = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=_auth_only(actor, "TREATMENT"),
        json=_pneumonia(str(uuid4())),
    )
    target = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_a.organization_id
    )
    iam_mismatch = await db_client.post(
        "/api/v1/iam/memberships",
        headers=_staff_headers(actor, hospital_a.organization_id, "ADMINISTRATION"),
        json={
            "user_id": str(target.user_id),
            "organization_id": str(hospital_b.organization_id),
            "role_code": RoleCode.ORG_ADMIN,
        },
    )
    iam_ok = await db_client.post(
        "/api/v1/iam/memberships",
        headers=_staff_headers(actor, hospital_a.organization_id, "ADMINISTRATION"),
        json={
            "user_id": str(target.user_id),
            "organization_id": str(hospital_a.organization_id),
            "role_code": RoleCode.ORG_ADMIN,
        },
    )
    assert mismatch_a_on_b.status_code == 403
    assert mismatch_b_on_a.status_code == 403
    assert no_header_b.status_code == 403
    assert no_header_a.status_code in {200, 201}
    assert clinical_no_header.status_code == 422
    assert iam_mismatch.status_code == 403
    assert iam_ok.status_code in {200, 201}
    assert "permissions" not in mismatch_a_on_b.text
    assert "ORG_ADMIN" not in mismatch_a_on_b.text


@requires_db
async def test_missing_membership_and_unknown_organization(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=actor.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    unknown = uuid4()
    missing = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=_staff_headers(actor, unknown),
        json=_pneumonia(patient_id),
    )
    other = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    foreign = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=_staff_headers(actor, other.organization_id),
        json=_pneumonia(patient_id),
    )
    facility = await db_client.post(
        f"/api/v1/organizations/{other.organization_id}/facilities",
        headers=_staff_headers(actor, other.organization_id, "ADMINISTRATION"),
        json=_facility_payload("No membership"),
    )
    assert missing.status_code in {403, 404}
    assert foreign.status_code in {403, 404}
    assert facility.status_code == 403
    me = await db_client.get("/api/v1/iam/users/me", headers=_staff_headers(actor, unknown))
    assert me.status_code == 200
    assert Permission.CLINICAL_CONDITION_CREATE not in me.json()["permissions"]


@requires_db
async def test_revoked_membership_is_excluded_from_projection(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.ORG_ADMIN,
    )
    actor = _as_actor(hospital_a)
    before = await db_client.post(
        f"/api/v1/organizations/{hospital_b.organization_id}/facilities",
        headers=_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
        json=_facility_payload("Before revoke"),
    )
    assert before.status_code in {200, 201}
    await _revoke_membership(db_engine, hospital_a.user_id, hospital_b.organization_id)
    after = await db_client.post(
        f"/api/v1/organizations/{hospital_b.organization_id}/facilities",
        headers=_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
        json=_facility_payload("After revoke"),
    )
    assert after.status_code == 403


@requires_db
async def test_same_org_multiple_memberships_union_roles_and_facilities(
    db_client, db_engine
) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    a1 = await _add_facility(db_engine, hospital_a.organization_id, "Dual A1")
    a2 = await _add_facility(db_engine, hospital_a.organization_id, "Dual A2")
    a3 = await _add_facility(db_engine, hospital_a.organization_id, "Dual A3")
    await _bind_membership_facility(db_engine, hospital_a.user_id, hospital_a.organization_id, a1)
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_a.organization_id,
        role_code=RoleCode.REGISTRAR,
        facility_id=a2,
    )
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_a.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    actor = _as_actor(hospital_a)
    condition = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=_staff_headers(actor, hospital_a.organization_id),
        json=_pneumonia(patient_id),
    )
    identity = await db_client.post(
        "/api/v1/mpi/identities",
        headers=_staff_headers(actor, hospital_a.organization_id, "REGISTRATION"),
        json={
            "given_name": "Dual",
            "family_name": "Member",
            "birth_date": "1990-01-01",
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": "NIK",
                    "identifier_value": unique_nik(),
                }
            ],
        },
    )
    chart_a1 = await db_client.get(
        f"/api/v1/clinical/patients/{patient_id}/chart",
        headers={**_staff_headers(actor, hospital_a.organization_id), "X-Facility-Id": str(a1)},
    )
    chart_a2 = await db_client.get(
        f"/api/v1/clinical/patients/{patient_id}/chart",
        headers={**_staff_headers(actor, hospital_a.organization_id), "X-Facility-Id": str(a2)},
    )
    chart_a3 = await db_client.get(
        f"/api/v1/clinical/patients/{patient_id}/chart",
        headers={**_staff_headers(actor, hospital_a.organization_id), "X-Facility-Id": str(a3)},
    )
    assert condition.status_code in {200, 201}
    assert identity.status_code in {200, 201}
    assert chart_a1.status_code == 200
    assert chart_a2.status_code == 200
    assert chart_a3.status_code in {403, 404}


@requires_db
async def test_platform_hybrid_phi_deny_and_tenant_non_phi(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    await _add_platform_membership(db_engine, hospital_a.user_id)
    actor = _as_actor(hospital_a)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_a.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    chart = await db_client.get(
        f"/api/v1/clinical/patients/{patient_id}/chart",
        headers=_staff_headers(actor, hospital_a.organization_id),
    )
    mpi = await db_client.get(
        f"/api/v1/mpi/identities/{patient_id}",
        headers=_staff_headers(actor, hospital_a.organization_id, "ADMINISTRATION"),
    )
    facility = await db_client.post(
        f"/api/v1/organizations/{hospital_a.organization_id}/facilities",
        headers=_staff_headers(actor, hospital_a.organization_id, "ADMINISTRATION"),
        json=_facility_payload("Hybrid A"),
    )
    foreign = await db_client.post(
        f"/api/v1/organizations/{hospital_b.organization_id}/facilities",
        headers=_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
        json=_facility_payload("Hybrid B"),
    )
    created = await db_client.post(
        "/api/v1/organizations",
        headers=_staff_headers(actor, hospital_a.organization_id, "ADMINISTRATION"),
        json={
            "name": f"Hybrid Org {new_id().hex[:8]}",
            "code": f"H{new_id().hex[:8].upper()}",
            "organization_type": "HOSPITAL",
        },
    )
    assert chart.status_code == 403
    assert mpi.status_code == 403
    assert facility.status_code in {200, 201}
    assert foreign.status_code == 403
    assert created.status_code in {200, 201}


@requires_db
async def test_platform_admin_org_header_does_not_become_tenant_staff(db_client, db_engine) -> None:
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    headers = {
        "Authorization": f"Bearer {platform.token}",
        "X-Organization-Id": str(clinician.organization_id),
        "X-Purpose": "TREATMENT",
    }
    chart = await db_client.get(f"/api/v1/clinical/patients/{patient_id}/chart", headers=headers)
    mpi = await db_client.get(
        f"/api/v1/mpi/identities/{patient_id}",
        headers={**headers, "X-Purpose": "ADMINISTRATION"},
    )
    facility = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/facilities",
        headers={**headers, "X-Purpose": "ADMINISTRATION"},
        json=_facility_payload("Platform as tenant"),
    )
    created = await db_client.post(
        "/api/v1/organizations",
        headers={**headers, "X-Purpose": "ADMINISTRATION"},
        json={
            "name": f"Platform Header {new_id().hex[:8]}",
            "code": f"PH{new_id().hex[:8].upper()}",
            "organization_type": "HOSPITAL",
        },
    )
    assert chart.status_code == 403
    assert mpi.status_code == 403
    assert facility.status_code == 403
    assert created.status_code in {200, 201}


@requires_db
async def test_three_org_and_role_switch_and_chart_sections(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    hospital_c = await seed_actor(db_engine, role_code=RoleCode.AUDITOR)
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.REGISTRAR,
    )
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_c.organization_id,
        role_code=RoleCode.AUDITOR,
    )
    actor = _as_actor(hospital_a)
    registrar_a = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_a.organization_id
    )
    registrar_c = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_c.organization_id
    )
    patient_a = await _active_patient(db_client, registrar_a)
    patient_b = await _active_patient(db_client, hospital_b)
    patient_c = await _active_patient(db_client, registrar_c)
    assert (
        await db_client.post(
            "/api/v1/clinical/conditions",
            headers=_staff_headers(actor, hospital_a.organization_id),
            json=_pneumonia(patient_a),
        )
    ).status_code in {200, 201}
    assert (
        await db_client.post(
            "/api/v1/clinical/conditions",
            headers=_staff_headers(actor, hospital_b.organization_id, "REGISTRATION"),
            json=_pneumonia(patient_b),
        )
    ).status_code == 403
    assert (
        await db_client.post(
            "/api/v1/clinical/conditions",
            headers=_staff_headers(actor, hospital_c.organization_id, "AUDIT"),
            json=_pneumonia(patient_c),
        )
    ).status_code == 403
    chart_a = await db_client.get(
        f"/api/v1/clinical/patients/{patient_a}/chart",
        headers=_staff_headers(actor, hospital_a.organization_id),
    )
    chart_b = await db_client.get(
        f"/api/v1/clinical/patients/{patient_b}/chart",
        headers=_staff_headers(actor, hospital_b.organization_id, "REGISTRATION"),
    )
    chart_a_again = await db_client.get(
        f"/api/v1/clinical/patients/{patient_a}/chart",
        headers=_staff_headers(actor, hospital_a.organization_id),
    )
    chart_c = await db_client.get(
        f"/api/v1/clinical/patients/{patient_c}/chart",
        headers=_staff_headers(actor, hospital_c.organization_id, "AUDIT"),
    )
    assert chart_a.status_code == 200
    assert "conditions" in chart_a.json()["authorized_sections"]
    assert chart_b.status_code == 200
    assert chart_b.json()["authorized_sections"] == ["encounters"]
    assert chart_a_again.json()["authorized_sections"] == chart_a.json()["authorized_sections"]
    assert chart_c.status_code == 200
    assert "conditions" in chart_c.json()["authorized_sections"]
    encounter_under_a = await _open_encounter(db_client, actor, patient_a)
    encounter_under_b = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=_staff_headers(actor, hospital_b.organization_id, "REGISTRATION"),
        json={"patient_identity_id": patient_b, "encounter_class": "AMB"},
    )
    assert encounter_under_a.status_code in {200, 201}
    assert encounter_under_b.status_code in {200, 201}


@requires_db
async def test_auditor_vs_clinician_and_registrar_vs_identity_officer(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.AUDITOR)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.CLINICIAN,
    )
    actor = _as_actor(hospital_a)
    registrar_a = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_a.organization_id
    )
    registrar_b = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_b.organization_id
    )
    patient_a = await _active_patient(db_client, registrar_a)
    patient_b = await _active_patient(db_client, registrar_b)
    assert (
        await db_client.post(
            "/api/v1/clinical/conditions",
            headers=_staff_headers(actor, hospital_a.organization_id, "AUDIT"),
            json=_pneumonia(patient_a),
        )
    ).status_code == 403
    assert (
        await db_client.post(
            "/api/v1/clinical/conditions",
            headers=_staff_headers(actor, hospital_b.organization_id),
            json=_pneumonia(patient_b),
        )
    ).status_code in {200, 201}

    registrar_home = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer_org = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    await _add_membership(
        db_engine,
        user_id=registrar_home.user_id,
        organization_id=officer_org.organization_id,
        role_code=RoleCode.IDENTITY_OFFICER,
    )
    mixed = _as_actor(registrar_home)
    patient_r = await _active_patient(db_client, registrar_home)
    encounter_r = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=_staff_headers(mixed, registrar_home.organization_id, "REGISTRATION"),
        json={"patient_identity_id": patient_r, "encounter_class": "AMB"},
    )
    merge_r = await db_client.post(
        "/api/v1/mpi/merge",
        headers=_staff_headers(mixed, registrar_home.organization_id, "IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": patient_r,
            "target_identity_id": patient_r,
            "reason": "must not merge as registrar",
            "evidence": merge_evidence("iso-reg"),
        },
    )
    encounter_o = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=_staff_headers(mixed, officer_org.organization_id, "IDENTITY_RESOLUTION"),
        json={"patient_identity_id": patient_r, "encounter_class": "AMB"},
    )
    assert encounter_r.status_code in {200, 201}
    assert merge_r.status_code == 403
    assert encounter_o.status_code == 403


@requires_db
async def test_concurrent_requests_use_independent_org_context(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.ORG_ADMIN,
    )
    actor = _as_actor(hospital_a)
    registrar_a = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_a.organization_id
    )
    registrar_b = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_b.organization_id
    )
    patient_a = await _active_patient(db_client, registrar_a)
    patient_b = await _active_patient(db_client, registrar_b)

    async def clinical_a():
        return await db_client.post(
            "/api/v1/clinical/conditions",
            headers=_staff_headers(actor, hospital_a.organization_id),
            json=_pneumonia(patient_a),
        )

    async def admin_b():
        return await db_client.post(
            f"/api/v1/organizations/{hospital_b.organization_id}/facilities",
            headers=_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
            json=_facility_payload("Concurrent B"),
        )

    async def admin_a():
        return await db_client.post(
            f"/api/v1/organizations/{hospital_a.organization_id}/facilities",
            headers=_staff_headers(actor, hospital_a.organization_id, "ADMINISTRATION"),
            json=_facility_payload("Concurrent A"),
        )

    async def clinical_b():
        return await db_client.post(
            "/api/v1/clinical/conditions",
            headers=_staff_headers(actor, hospital_b.organization_id),
            json=_pneumonia(patient_b),
        )

    for _ in range(3):
        clinical, facility_b, facility_a, write_b = await asyncio.gather(
            clinical_a(), admin_b(), admin_a(), clinical_b()
        )
        assert clinical.status_code in {200, 201}
        assert facility_b.status_code in {200, 201}
        assert facility_a.status_code == 403
        assert write_b.status_code == 403


@requires_db
async def test_empty_facility_scope_stays_org_local(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    a1 = await _add_facility(db_engine, hospital_a.organization_id, "Empty A1")
    a2 = await _add_facility(db_engine, hospital_a.organization_id, "Empty A2")
    b1 = await _add_facility(db_engine, hospital_b.organization_id, "Empty B1")
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.CLINICIAN,
        facility_id=b1,
    )
    actor = _as_actor(hospital_a)
    registrar_a = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_a.organization_id
    )
    registrar_b = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_b.organization_id
    )
    patient_a = await _active_patient(db_client, registrar_a)
    patient_b = await _active_patient(db_client, registrar_b)
    for facility_id in (a1, a2):
        allowed = await db_client.get(
            f"/api/v1/clinical/patients/{patient_a}/chart",
            headers={
                **_staff_headers(actor, hospital_a.organization_id),
                "X-Facility-Id": str(facility_id),
            },
        )
        assert allowed.status_code == 200
    assert (
        await db_client.get(
            f"/api/v1/clinical/patients/{patient_a}/chart",
            headers={**_staff_headers(actor, hospital_a.organization_id), "X-Facility-Id": str(b1)},
        )
    ).status_code in {403, 404}
    assert (
        await db_client.get(
            f"/api/v1/clinical/patients/{patient_b}/chart",
            headers={**_staff_headers(actor, hospital_b.organization_id), "X-Facility-Id": str(b1)},
        )
    ).status_code == 200
    assert (
        await db_client.get(
            f"/api/v1/clinical/patients/{patient_b}/chart",
            headers={**_staff_headers(actor, hospital_b.organization_id), "X-Facility-Id": str(a1)},
        )
    ).status_code in {403, 404}
