from uuid import UUID

import pytest
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.iam.domain.enums import MembershipStatus
from app.modules.iam.infrastructure.models import OrganizationMembershipModel, RoleModel
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel
from app.shared.types.ids import new_id
from sqlalchemy import select
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.test_wave2a_hardening import _active_patient
from tests.integration.test_wave2b1_condition import _pneumonia

pytestmark = pytest.mark.integration


def _staff_headers(
    actor: SeededActor, organization_id: UUID, purpose: str = "TREATMENT"
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {actor.token}",
        "X-Organization-Id": str(organization_id),
        "X-Purpose": purpose,
    }


def _as_actor(source: SeededActor) -> SeededActor:
    return SeededActor(source.user_id, source.subject, source.organization_id, source.token)


async def _add_membership(
    db_engine,
    *,
    user_id: UUID,
    organization_id: UUID,
    role_code: str,
    facility_id: UUID | None = None,
) -> None:
    async with db_engine.begin() as connection:
        role_id = (
            await connection.execute(select(RoleModel.id).where(RoleModel.code == role_code))
        ).scalar_one()
        await connection.execute(
            OrganizationMembershipModel.__table__.insert().values(
                id=new_id(),
                user_id=user_id,
                organization_id=organization_id,
                facility_id=facility_id,
                role_id=role_id,
                status=MembershipStatus.ACTIVE,
            )
        )


async def _bind_membership_facility(
    db_engine, user_id: UUID, organization_id: UUID, facility_id: UUID
) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(
            OrganizationMembershipModel.__table__.update()
            .where(
                OrganizationMembershipModel.user_id == user_id,
                OrganizationMembershipModel.organization_id == organization_id,
            )
            .values(facility_id=facility_id)
        )


async def _add_facility(db_engine, organization_id: UUID, name: str) -> UUID:
    facility_id = new_id()
    async with db_engine.begin() as connection:
        await connection.execute(
            FacilityModel.__table__.insert().values(
                id=facility_id,
                organization_id=organization_id,
                name=name,
                code=f"F{facility_id.hex[:10].upper()}",
                facility_type=FacilityType.HOSPITAL_SITE,
                status=FacilityStatus.ACTIVE,
            )
        )
    return facility_id


def _facility_payload(name: str) -> dict[str, str]:
    suffix = new_id().hex[:8].upper()
    return {"name": name, "code": f"FX{suffix}", "facility_type": "HOSPITAL_SITE"}


@requires_db
async def test_multi_org_clinician_admin_permission_isolation(db_client, db_engine) -> None:
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

    created_a = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=_staff_headers(actor, hospital_a.organization_id),
        json=_pneumonia(patient_a),
    )
    created_b = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=_staff_headers(actor, hospital_b.organization_id),
        json=_pneumonia(patient_b),
    )
    assert created_a.status_code in {200, 201}
    assert created_b.status_code == 403

    facility_a = await db_client.post(
        f"/api/v1/organizations/{hospital_a.organization_id}/facilities",
        headers=_staff_headers(actor, hospital_a.organization_id, "ADMINISTRATION"),
        json=_facility_payload("Ward A"),
    )
    facility_b = await db_client.post(
        f"/api/v1/organizations/{hospital_b.organization_id}/facilities",
        headers=_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
        json=_facility_payload("Ward B"),
    )
    assert facility_a.status_code == 403
    assert facility_b.status_code in {200, 201}

    me_a = await db_client.get(
        "/api/v1/iam/users/me", headers=_staff_headers(actor, hospital_a.organization_id)
    )
    me_b = await db_client.get(
        "/api/v1/iam/users/me", headers=_staff_headers(actor, hospital_b.organization_id)
    )
    assert Permission.CLINICAL_CONDITION_CREATE in me_a.json()["permissions"]
    assert Permission.ORG_FACILITY_CREATE not in me_a.json()["permissions"]
    assert Permission.ORG_FACILITY_CREATE in me_b.json()["permissions"]
    assert Permission.CLINICAL_CONDITION_CREATE not in me_b.json()["permissions"]

    chart_a = await db_client.get(
        f"/api/v1/clinical/patients/{patient_a}/chart",
        headers=_staff_headers(actor, hospital_a.organization_id),
    )
    chart_b = await db_client.get(
        f"/api/v1/clinical/patients/{patient_b}/chart",
        headers=_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
    )
    assert chart_a.status_code == 200
    assert "conditions" in chart_a.json()["authorized_sections"]
    assert chart_b.status_code == 200
    assert "conditions" in chart_b.json()["authorized_sections"]


@requires_db
async def test_multi_org_reverse_admin_clinician_isolation(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
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
            headers=_staff_headers(actor, hospital_a.organization_id),
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
    assert (
        await db_client.post(
            f"/api/v1/organizations/{hospital_a.organization_id}/facilities",
            headers=_staff_headers(actor, hospital_a.organization_id, "ADMINISTRATION"),
            json=_facility_payload("Admin A"),
        )
    ).status_code in {200, 201}
    assert (
        await db_client.post(
            f"/api/v1/organizations/{hospital_b.organization_id}/facilities",
            headers=_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
            json=_facility_payload("Admin B"),
        )
    ).status_code == 403


@requires_db
async def test_three_org_permission_isolation(db_client, db_engine) -> None:
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
    chart_b = await db_client.get(
        f"/api/v1/clinical/patients/{patient_b}/chart",
        headers=_staff_headers(actor, hospital_b.organization_id, "REGISTRATION"),
    )
    chart_c = await db_client.get(
        f"/api/v1/clinical/patients/{patient_c}/chart",
        headers=_staff_headers(actor, hospital_c.organization_id, "AUDIT"),
    )
    me_a = await db_client.get(
        "/api/v1/iam/users/me", headers=_staff_headers(actor, hospital_a.organization_id)
    )
    assert Permission.CLINICAL_CONDITION_CREATE in me_a.json()["permissions"]
    assert Permission.MPI_IDENTITY_CREATE not in me_a.json()["permissions"]
    assert chart_b.status_code == 200
    assert chart_b.json()["authorized_sections"] == ["encounters"]
    assert chart_c.status_code == 200
    assert "conditions" in chart_c.json()["authorized_sections"]
    assert "encounters" in chart_c.json()["authorized_sections"]


@requires_db
async def test_multi_org_facility_scope_and_header_tamper(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    a1 = await _add_facility(db_engine, hospital_a.organization_id, "A1")
    a2 = await _add_facility(db_engine, hospital_a.organization_id, "A2")
    b1 = await _add_facility(db_engine, hospital_b.organization_id, "B1")
    b2 = await _add_facility(db_engine, hospital_b.organization_id, "B2")
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.CLINICIAN,
        facility_id=b2,
    )
    await _bind_membership_facility(db_engine, hospital_a.user_id, hospital_a.organization_id, a1)
    actor = _as_actor(hospital_a)
    registrar_a = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_a.organization_id
    )
    registrar_b = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital_b.organization_id
    )
    patient_a = await _active_patient(db_client, registrar_a)
    patient_b = await _active_patient(db_client, registrar_b)
    ok_a1 = await db_client.get(
        f"/api/v1/clinical/patients/{patient_a}/chart",
        headers={**_staff_headers(actor, hospital_a.organization_id), "X-Facility-Id": str(a1)},
    )
    deny_a2 = await db_client.get(
        f"/api/v1/clinical/patients/{patient_a}/chart",
        headers={**_staff_headers(actor, hospital_a.organization_id), "X-Facility-Id": str(a2)},
    )
    tamper_b1 = await db_client.get(
        f"/api/v1/clinical/patients/{patient_a}/chart",
        headers={**_staff_headers(actor, hospital_a.organization_id), "X-Facility-Id": str(b1)},
    )
    tamper_b2 = await db_client.get(
        f"/api/v1/clinical/patients/{patient_a}/chart",
        headers={**_staff_headers(actor, hospital_a.organization_id), "X-Facility-Id": str(b2)},
    )
    tamper_a1_on_b = await db_client.get(
        f"/api/v1/clinical/patients/{patient_b}/chart",
        headers={**_staff_headers(actor, hospital_b.organization_id), "X-Facility-Id": str(a1)},
    )
    ok_b2 = await db_client.get(
        f"/api/v1/clinical/patients/{patient_b}/chart",
        headers={**_staff_headers(actor, hospital_b.organization_id), "X-Facility-Id": str(b2)},
    )
    deny_b1 = await db_client.get(
        f"/api/v1/clinical/patients/{patient_b}/chart",
        headers={**_staff_headers(actor, hospital_b.organization_id), "X-Facility-Id": str(b1)},
    )
    assert ok_a1.status_code == 200
    assert deny_a2.status_code in {403, 404}
    assert tamper_b1.status_code in {403, 404}
    assert tamper_b2.status_code in {403, 404}
    assert tamper_a1_on_b.status_code in {403, 404}
    assert ok_b2.status_code == 200
    assert deny_b1.status_code in {403, 404}


@requires_db
async def test_empty_facility_scope_is_org_local_not_global(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    a1 = await _add_facility(db_engine, hospital_a.organization_id, "Site A1")
    a2 = await _add_facility(db_engine, hospital_a.organization_id, "Site A2")
    b1 = await _add_facility(db_engine, hospital_b.organization_id, "Site B1")
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
    denied_b1_on_a = await db_client.get(
        f"/api/v1/clinical/patients/{patient_a}/chart",
        headers={**_staff_headers(actor, hospital_a.organization_id), "X-Facility-Id": str(b1)},
    )
    ok_b1 = await db_client.get(
        f"/api/v1/clinical/patients/{patient_b}/chart",
        headers={**_staff_headers(actor, hospital_b.organization_id), "X-Facility-Id": str(b1)},
    )
    denied_a1_on_b = await db_client.get(
        f"/api/v1/clinical/patients/{patient_b}/chart",
        headers={**_staff_headers(actor, hospital_b.organization_id), "X-Facility-Id": str(a1)},
    )
    assert denied_b1_on_a.status_code in {403, 404}
    assert ok_b1.status_code == 200
    assert denied_a1_on_b.status_code in {403, 404}


@requires_db
async def test_mixed_permission_and_facility_combination(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    a1 = await _add_facility(db_engine, hospital_a.organization_id, "Combo A1")
    a2 = await _add_facility(db_engine, hospital_a.organization_id, "Combo A2")
    b1 = await _add_facility(db_engine, hospital_b.organization_id, "Combo B1")
    await _bind_membership_facility(db_engine, hospital_a.user_id, hospital_a.organization_id, a1)
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.ORG_ADMIN,
        facility_id=None,
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
            headers=_staff_headers(actor, hospital_a.organization_id),
            json=_pneumonia(patient_a),
        )
    ).status_code in {200, 201}
    assert (
        await db_client.post(
            "/api/v1/clinical/conditions",
            headers=_staff_headers(actor, hospital_b.organization_id),
            json=_pneumonia(patient_b),
        )
    ).status_code == 403
    assert (
        await db_client.post(
            f"/api/v1/organizations/{hospital_a.organization_id}/facilities",
            headers=_staff_headers(actor, hospital_a.organization_id, "ADMINISTRATION"),
            json=_facility_payload("Combo deny A"),
        )
    ).status_code == 403
    assert (
        await db_client.post(
            f"/api/v1/organizations/{hospital_b.organization_id}/facilities",
            headers=_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
            json=_facility_payload("Combo allow B"),
        )
    ).status_code in {200, 201}
    assert (
        await db_client.get(
            f"/api/v1/clinical/patients/{patient_a}/chart",
            headers={**_staff_headers(actor, hospital_a.organization_id), "X-Facility-Id": str(a1)},
        )
    ).status_code == 200
    assert (
        await db_client.get(
            f"/api/v1/clinical/patients/{patient_a}/chart",
            headers={**_staff_headers(actor, hospital_a.organization_id), "X-Facility-Id": str(a2)},
        )
    ).status_code in {403, 404}
    assert (
        await db_client.get(
            f"/api/v1/clinical/patients/{patient_b}/chart",
            headers={
                **_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
                "X-Facility-Id": str(b1),
            },
        )
    ).status_code == 200
    assert (
        await db_client.get(
            f"/api/v1/clinical/patients/{patient_b}/chart",
            headers={
                **_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
                "X-Facility-Id": str(a1),
            },
        )
    ).status_code in {403, 404}


@requires_db
async def test_platform_admin_phi_deny_unchanged_with_organization_header(
    db_client, db_engine
) -> None:
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    denied = await db_client.get(
        f"/api/v1/clinical/patients/{patient_id}/chart",
        headers={
            "Authorization": f"Bearer {platform.token}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert denied.status_code == 403
    created = await db_client.post(
        "/api/v1/organizations",
        headers=platform.headers(purpose="ADMINISTRATION"),
        json={
            "name": f"Platform Org {new_id().hex[:8]}",
            "code": f"P{new_id().hex[:8].upper()}",
            "organization_type": "HOSPITAL",
        },
    )
    assert created.status_code in {200, 201}
