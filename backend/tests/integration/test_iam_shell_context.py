from uuid import UUID, uuid4

import pytest
from app.modules.authorization.domain.catalog import ROLE_PERMISSIONS, Permission, RoleCode
from app.modules.iam.domain.enums import MembershipStatus
from app.modules.iam.infrastructure.models import OrganizationMembershipModel
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel
from app.shared.types.ids import new_id
from sqlalchemy import text
from tests.conftest import mint_token
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.test_clinical_read_core import _chart
from tests.integration.test_product_access_multi_org_isolation import (
    _add_facility,
    _add_membership,
    _as_actor,
    _bind_membership_facility,
)
from tests.integration.test_wave2a_hardening import _active_patient

pytestmark = pytest.mark.integration

_ORGS = "/api/v1/iam/me/organizations"
_CONTEXT = "/api/v1/iam/me/context"
_PHI_MARKERS = ("mrn", "nik", "bpjs", "patient_name", "encounter_id", "canonical_patient")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _org_headers(actor: SeededActor, organization_id: UUID) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {actor.token}",
        "X-Organization-Id": str(organization_id),
    }


def _accessible(organization_id: UUID) -> str:
    return f"/api/v1/organizations/{organization_id}/facilities/accessible"


def _ids(payload: list[dict[str, object]], key: str) -> list[str]:
    return [str(item[key]) for item in payload]


def _assert_no_phi(payload: object) -> None:
    raw = str(payload).lower()
    for marker in _PHI_MARKERS:
        assert marker not in raw


async def _provenance_count(db_engine) -> int:
    async with db_engine.connect() as connection:
        return int(
            (
                await connection.execute(text("SELECT count(*) FROM clinical_provenances"))
            ).scalar_one()
        )


async def _revoke_membership(db_engine, user_id: UUID, organization_id: UUID) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(
            OrganizationMembershipModel.__table__.update()
            .where(
                OrganizationMembershipModel.user_id == user_id,
                OrganizationMembershipModel.organization_id == organization_id,
            )
            .values(status=MembershipStatus.REVOKED)
        )


async def _add_inactive_facility(db_engine, organization_id: UUID, name: str) -> UUID:
    facility_id = new_id()
    async with db_engine.begin() as connection:
        await connection.execute(
            FacilityModel.__table__.insert().values(
                id=facility_id,
                organization_id=organization_id,
                name=name,
                code=f"I{facility_id.hex[:10].upper()}",
                facility_type=FacilityType.HOSPITAL_SITE,
                status=FacilityStatus.INACTIVE,
            )
        )
    return facility_id


@requires_db
async def test_single_org_staff_shell_context(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    listed = await db_client.get(_ORGS, headers=_auth(actor.token))
    assert listed.status_code == 200
    body = listed.json()
    assert body["provisioned"] is True
    assert body["user"]["subject"] == actor.subject
    assert _ids(body["organizations"], "organization_id") == [str(actor.organization_id)]
    assert body["organizations"][0]["role_codes"] == [RoleCode.CLINICIAN]
    _assert_no_phi(body)

    context = await db_client.get(_CONTEXT, headers=_org_headers(actor, actor.organization_id))
    assert context.status_code == 200
    ctx = context.json()
    assert ctx["facility_scope"] == "ALL_IN_ORGANIZATION"
    assert ctx["work_facility_required"] is False
    assert ctx["effective_permissions"] == sorted(ROLE_PERMISSIONS[RoleCode.CLINICIAN])
    assert ctx["effective_permissions"] == sorted(set(ctx["effective_permissions"]))
    assert "accessible_facilities" not in ctx
    _assert_no_phi(ctx)

    facilities = await db_client.get(
        _accessible(actor.organization_id),
        headers=_org_headers(actor, actor.organization_id),
    )
    assert facilities.status_code == 200
    assert facilities.json()["facility_scope"] == "ALL_IN_ORGANIZATION"
    assert facilities.json()["facilities"] == []


@requires_db
async def test_multi_org_permission_isolation_and_three_org_roles(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    hospital_c = await seed_actor(db_engine, role_code=RoleCode.AUDITOR)
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.ORG_ADMIN,
    )
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_c.organization_id,
        role_code=RoleCode.AUDITOR,
    )
    actor = _as_actor(hospital_a)

    listed = await db_client.get(_ORGS, headers=_auth(actor.token))
    assert listed.status_code == 200
    organizations = listed.json()["organizations"]
    org_ids = _ids(organizations, "organization_id")
    assert set(org_ids) == {
        str(hospital_a.organization_id),
        str(hospital_b.organization_id),
        str(hospital_c.organization_id),
    }
    sort_keys = [
        (item["name"].lower(), item["code"], item["organization_id"]) for item in organizations
    ]
    assert sort_keys == sorted(sort_keys)

    ctx_a = (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, hospital_a.organization_id))
    ).json()
    ctx_b = (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, hospital_b.organization_id))
    ).json()
    ctx_c = (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, hospital_c.organization_id))
    ).json()
    assert ctx_a["role_codes"] == [RoleCode.CLINICIAN]
    assert ctx_b["role_codes"] == [RoleCode.ORG_ADMIN]
    assert ctx_c["role_codes"] == [RoleCode.AUDITOR]
    assert ctx_a["effective_permissions"] == sorted(ROLE_PERMISSIONS[RoleCode.CLINICIAN])
    assert ctx_b["effective_permissions"] == sorted(ROLE_PERMISSIONS[RoleCode.ORG_ADMIN])
    assert ctx_c["effective_permissions"] == sorted(ROLE_PERMISSIONS[RoleCode.AUDITOR])
    assert Permission.CLINICAL_CONDITION_CREATE in ctx_a["effective_permissions"]
    assert Permission.CLINICAL_CONDITION_CREATE not in ctx_b["effective_permissions"]
    assert Permission.CLINICAL_CONDITION_CREATE not in ctx_c["effective_permissions"]
    assert Permission.IAM_MEMBERSHIP_MANAGE in ctx_b["effective_permissions"]
    assert Permission.IAM_MEMBERSHIP_MANAGE not in ctx_a["effective_permissions"]
    assert Permission.ORG_FACILITY_CREATE not in ctx_a["effective_permissions"]
    assert Permission.MPI_IDENTITY_CREATE not in ctx_a["effective_permissions"]
    assert Permission.MPI_IDENTITY_CREATE not in ctx_c["effective_permissions"]


@requires_db
async def test_revoked_and_missing_membership_concealed(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.ORG_ADMIN,
    )
    actor = _as_actor(hospital_a)
    await _revoke_membership(db_engine, actor.user_id, hospital_b.organization_id)

    listed = await db_client.get(_ORGS, headers=_auth(actor.token))
    assert _ids(listed.json()["organizations"], "organization_id") == [str(actor.organization_id)]

    revoked_ctx = await db_client.get(
        _CONTEXT, headers=_org_headers(actor, hospital_b.organization_id)
    )
    assert revoked_ctx.status_code == 404
    revoked_facilities = await db_client.get(
        _accessible(hospital_b.organization_id),
        headers=_org_headers(actor, hospital_b.organization_id),
    )
    assert revoked_facilities.status_code == 404

    outsider = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    missing = await db_client.get(_CONTEXT, headers=_org_headers(actor, outsider.organization_id))
    assert missing.status_code == 404
    unknown = uuid4()
    assert (await db_client.get(_CONTEXT, headers=_org_headers(actor, unknown))).status_code == 404
    assert (
        await db_client.get(_accessible(unknown), headers=_org_headers(actor, unknown))
    ).status_code == 404


@requires_db
async def test_explicit_all_in_org_and_same_org_facility_union(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    site_b = await _add_facility(db_engine, actor.organization_id, "Site B")
    site_a = await _add_facility(db_engine, actor.organization_id, "Site A")
    inactive = await _add_inactive_facility(db_engine, actor.organization_id, "Site Inactive")

    all_in = await db_client.get(
        _accessible(actor.organization_id),
        headers=_org_headers(actor, actor.organization_id),
    )
    assert all_in.status_code == 200
    all_body = all_in.json()
    assert all_body["facility_scope"] == "ALL_IN_ORGANIZATION"
    assert _ids(all_body["facilities"], "id") == [str(site_a), str(site_b)]
    assert str(inactive) not in _ids(all_body["facilities"], "id")
    names = [item["name"] for item in all_body["facilities"]]
    assert names == sorted(names)
    ctx_all = (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, actor.organization_id))
    ).json()
    assert ctx_all["facility_scope"] == "ALL_IN_ORGANIZATION"
    assert ctx_all["work_facility_required"] is False

    await _bind_membership_facility(db_engine, actor.user_id, actor.organization_id, site_a)
    explicit = await db_client.get(
        _accessible(actor.organization_id),
        headers=_org_headers(actor, actor.organization_id),
    )
    assert explicit.json()["facility_scope"] == "EXPLICIT"
    assert _ids(explicit.json()["facilities"], "id") == [str(site_a)]
    ctx_explicit = (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, actor.organization_id))
    ).json()
    assert ctx_explicit["facility_scope"] == "EXPLICIT"
    assert ctx_explicit["work_facility_required"] is True

    await _add_membership(
        db_engine,
        user_id=actor.user_id,
        organization_id=actor.organization_id,
        role_code=RoleCode.REGISTRAR,
        facility_id=site_b,
    )
    unioned = await db_client.get(
        _accessible(actor.organization_id),
        headers=_org_headers(actor, actor.organization_id),
    )
    assert unioned.json()["facility_scope"] == "EXPLICIT"
    assert _ids(unioned.json()["facilities"], "id") == [str(site_a), str(site_b)]
    ctx_union = (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, actor.organization_id))
    ).json()
    assert sorted(ctx_union["role_codes"]) == [RoleCode.CLINICIAN, RoleCode.REGISTRAR]
    assert ctx_union["facility_scope"] == "EXPLICIT"

    await _add_membership(
        db_engine,
        user_id=actor.user_id,
        organization_id=actor.organization_id,
        role_code=RoleCode.AUDITOR,
        facility_id=None,
    )
    org_wide = await db_client.get(
        _accessible(actor.organization_id),
        headers=_org_headers(actor, actor.organization_id),
    )
    assert org_wide.json()["facility_scope"] == "ALL_IN_ORGANIZATION"
    assert _ids(org_wide.json()["facilities"], "id") == [str(site_a), str(site_b)]
    assert (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, actor.organization_id))
    ).json()["facility_scope"] == "ALL_IN_ORGANIZATION"


@requires_db
async def test_cross_org_facilities_and_header_path_mismatch(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    site_a = await _add_facility(db_engine, hospital_a.organization_id, "A1")
    site_b = await _add_facility(db_engine, hospital_b.organization_id, "B1")
    await _bind_membership_facility(
        db_engine, hospital_a.user_id, hospital_a.organization_id, site_a
    )
    await _bind_membership_facility(
        db_engine, hospital_b.user_id, hospital_b.organization_id, site_b
    )
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.REGISTRAR,
        facility_id=site_b,
    )
    actor = _as_actor(hospital_a)

    listed_a = await db_client.get(
        _accessible(hospital_a.organization_id),
        headers=_org_headers(actor, hospital_a.organization_id),
    )
    listed_b = await db_client.get(
        _accessible(hospital_b.organization_id),
        headers=_org_headers(actor, hospital_b.organization_id),
    )
    assert _ids(listed_a.json()["facilities"], "id") == [str(site_a)]
    assert _ids(listed_b.json()["facilities"], "id") == [str(site_b)]
    assert str(site_b) not in _ids(listed_a.json()["facilities"], "id")
    assert str(site_a) not in _ids(listed_b.json()["facilities"], "id")

    mismatch_ab = await db_client.get(
        _accessible(hospital_b.organization_id),
        headers=_org_headers(actor, hospital_a.organization_id),
    )
    mismatch_ba = await db_client.get(
        _accessible(hospital_a.organization_id),
        headers=_org_headers(actor, hospital_b.organization_id),
    )
    assert mismatch_ab.status_code == 404
    assert mismatch_ba.status_code == 404
    assert str(site_b) not in str(mismatch_ab.json())
    assert str(site_a) not in str(mismatch_ba.json())


@requires_db
async def test_platform_only_hybrid_and_audience_boundaries(db_client, db_engine) -> None:
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    listed = await db_client.get(_ORGS, headers=_auth(platform.token))
    assert listed.status_code == 200
    assert listed.json()["provisioned"] is True
    assert listed.json()["organizations"] == []

    dummy = await db_client.get(_CONTEXT, headers=_org_headers(platform, platform.organization_id))
    assert dummy.status_code == 404
    assert (
        await db_client.get(
            _accessible(platform.organization_id),
            headers=_org_headers(platform, platform.organization_id),
        )
    ).status_code == 404

    tenant = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    await _add_membership(
        db_engine,
        user_id=platform.user_id,
        organization_id=tenant.organization_id,
        role_code=RoleCode.ORG_ADMIN,
    )
    hybrid_orgs = await db_client.get(_ORGS, headers=_auth(platform.token))
    assert _ids(hybrid_orgs.json()["organizations"], "organization_id") == [
        str(tenant.organization_id)
    ]
    hybrid_ctx = (
        await db_client.get(_CONTEXT, headers=_org_headers(platform, tenant.organization_id))
    ).json()
    assert hybrid_ctx["role_codes"] == [RoleCode.ORG_ADMIN]
    assert hybrid_ctx["effective_permissions"] == sorted(ROLE_PERMISSIONS[RoleCode.ORG_ADMIN])
    assert Permission.IAM_PLATFORM not in hybrid_ctx["effective_permissions"]
    assert Permission.ORG_ORGANIZATION_CREATE not in hybrid_ctx["effective_permissions"]

    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_headers = {
        "Authorization": f"Bearer {mint_token(sub=clinician.subject, aud='php-patient')}"
    }
    platform_headers = {
        "Authorization": f"Bearer {mint_token(sub=clinician.subject, aud='php-platform')}"
    }
    for headers in (patient_headers, platform_headers):
        assert (await db_client.get(_ORGS, headers=headers)).status_code == 401
        assert (
            await db_client.get(
                _CONTEXT, headers={**headers, "X-Organization-Id": str(clinician.organization_id)}
            )
        ).status_code == 401
        assert (
            await db_client.get(
                _accessible(clinician.organization_id),
                headers={**headers, "X-Organization-Id": str(clinician.organization_id)},
            )
        ).status_code == 401

    staff = await db_client.get(_ORGS, headers=_auth(clinician.token))
    assert staff.status_code == 200
    me = await db_client.get("/api/v1/iam/users/me", headers=_auth(clinician.token))
    assert me.status_code == 200
    assert set(me.json()) == {
        "provisioned",
        "id",
        "subject",
        "display_name",
        "roles",
        "permissions",
    }

    missing_header = await db_client.get(_CONTEXT, headers=_auth(clinician.token))
    assert missing_header.status_code == 422


@requires_db
async def test_shell_context_has_no_clinical_phi_or_provenance(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient = await _active_patient(db_client, registrar)
    before = await _provenance_count(db_engine)
    listed = await db_client.get(_ORGS, headers=_auth(clinician.token))
    ctx = await db_client.get(_CONTEXT, headers=_org_headers(clinician, clinician.organization_id))
    facilities = await db_client.get(
        _accessible(clinician.organization_id),
        headers=_org_headers(clinician, clinician.organization_id),
    )
    chart = await db_client.get(
        _chart(patient),
        headers={
            **_org_headers(clinician, clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    after = await _provenance_count(db_engine)
    assert listed.status_code == 200
    assert ctx.status_code == 200
    assert facilities.status_code == 200
    assert chart.status_code == 200
    assert after == before
    for payload in (listed.json(), ctx.json(), facilities.json()):
        _assert_no_phi(payload)
        assert "password" not in str(payload).lower()
        assert "token" not in str(payload).lower()
        assert "role_id" not in str(payload)
        assert "revoked_at" not in str(payload)
        assert "matching_value" not in str(payload)
