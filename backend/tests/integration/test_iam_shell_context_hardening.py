import asyncio
import hashlib
import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import jwt
import pytest
from app.modules.authorization.domain.catalog import ROLE_PERMISSIONS, Permission, RoleCode
from app.modules.iam.application import shell_context as shell_context_mod
from app.modules.iam.domain.enums import MembershipStatus
from app.modules.iam.infrastructure.models import OrganizationMembershipModel, RoleModel
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel, OrganizationModel
from app.shared.types.ids import new_id
from sqlalchemy import event, select, text
from tests.conftest import TEST_SECRET, mint_token
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_iam_shell_context import (
    _CONTEXT,
    _ORGS,
    _accessible,
    _assert_no_phi,
    _auth,
    _ids,
    _org_headers,
    _provenance_count,
)
from tests.integration.test_product_access_multi_org_isolation import (
    _add_facility,
    _add_membership,
    _as_actor,
    _bind_membership_facility,
    _facility_payload,
    _staff_headers,
)
from tests.integration.test_wave2a_hardening import _active_patient
from tests.integration.test_wave2b1_condition import _pneumonia

pytestmark = pytest.mark.integration

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
WAVE1_SHA256 = "f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd"
PRODUCT_ACCESS_SHA256 = "65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc"
_FORBIDDEN_KEYS = (
    "password",
    "token",
    "role_id",
    "revoked_at",
    "matching_value",
    "address_text",
    "membership_id",
    "audit_id",
    "provenance_id",
    "billing",
    "subscription",
)


def test_frozen_pdps_and_no_shell_cache() -> None:
    wave1 = APP_ROOT / "modules" / "authorization" / "application" / "wave1_pdp.py"
    product = APP_ROOT / "modules" / "authorization" / "application" / "product_access_pdp.py"
    assert hashlib.sha256(wave1.read_bytes()).hexdigest() == WAVE1_SHA256
    assert hashlib.sha256(product.read_bytes()).hexdigest() == PRODUCT_ACCESS_SHA256
    source = inspect.getsource(shell_context_mod)
    assert "redis" not in source.lower()
    assert "lru_cache" not in source
    assert "@cache" not in source


def _conceal(response) -> None:
    assert response.status_code == 404
    body = response.json()["error"]
    assert body["code"] == "not_found"
    assert body["message"] == "Resource not found"
    assert "membership" not in body["message"].lower()
    assert "sql" not in str(body).lower()


async def _count(db_engine, sql: str) -> int:
    async with db_engine.connect() as connection:
        return int((await connection.execute(text(sql))).scalar_one())


async def _revoke_role_membership(
    db_engine, user_id: UUID, organization_id: UUID, role_code: str
) -> None:
    async with db_engine.begin() as connection:
        role_id = (
            await connection.execute(select(RoleModel.id).where(RoleModel.code == role_code))
        ).scalar_one()
        await connection.execute(
            OrganizationMembershipModel.__table__.update()
            .where(
                OrganizationMembershipModel.user_id == user_id,
                OrganizationMembershipModel.organization_id == organization_id,
                OrganizationMembershipModel.role_id == role_id,
            )
            .values(status=MembershipStatus.REVOKED)
        )


async def _set_membership_facility(
    db_engine,
    user_id: UUID,
    organization_id: UUID,
    role_code: str,
    facility_id: UUID,
) -> None:
    async with db_engine.begin() as connection:
        role_id = (
            await connection.execute(select(RoleModel.id).where(RoleModel.code == role_code))
        ).scalar_one()
        await connection.execute(
            OrganizationMembershipModel.__table__.update()
            .where(
                OrganizationMembershipModel.user_id == user_id,
                OrganizationMembershipModel.organization_id == organization_id,
                OrganizationMembershipModel.role_id == role_id,
            )
            .values(facility_id=facility_id)
        )


async def _set_org_name(db_engine, organization_id: UUID, name: str) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(
            OrganizationModel.__table__.update()
            .where(OrganizationModel.id == organization_id)
            .values(name=name)
        )


def _assert_minimized(payload: object) -> None:
    raw = str(payload).lower()
    _assert_no_phi(payload)
    for key in _FORBIDDEN_KEYS:
        assert key not in raw
    if isinstance(payload, dict):
        assert "accessible_facilities" not in payload


@requires_db
async def test_unsupported_methods_and_missing_auth(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    paths = (
        _ORGS,
        _CONTEXT,
        _accessible(actor.organization_id),
    )
    for path in paths:
        assert (await db_client.get(path)).status_code == 401
        for method in ("post", "put", "patch", "delete"):
            response = await getattr(db_client, method)(path, headers=_auth(actor.token))
            assert response.status_code in {404, 405}
            assert "traceback" not in response.text.lower()


@requires_db
async def test_audience_matrix_and_malformed_tokens(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    org = str(actor.organization_id)
    paths = (
        (_ORGS, _auth(actor.token)),
        (_CONTEXT, {**_auth(actor.token), "X-Organization-Id": org}),
        (_accessible(actor.organization_id), {**_auth(actor.token), "X-Organization-Id": org}),
    )
    for path, headers in paths:
        assert (await db_client.get(path, headers=headers)).status_code == 200

    tokens = {
        "patient": mint_token(sub=actor.subject, aud="php-patient"),
        "platform": mint_token(sub=actor.subject, aud="php-platform"),
        "wrong": mint_token(sub=actor.subject, aud="other-api"),
        "mixed": mint_token(sub=actor.subject, extra={"aud": ["php-api", "php-patient"]}),
        "missing": jwt.encode(
            {
                "sub": actor.subject,
                "iss": "http://localhost:8080/realms/php-dev",
                "exp": datetime.now(UTC) + timedelta(minutes=5),
                "iat": datetime.now(UTC),
            },
            TEST_SECRET,
            algorithm="HS256",
        ),
        "malformed": "not-a-jwt",
    }
    for token in tokens.values():
        for path in (_ORGS, _CONTEXT, _accessible(actor.organization_id)):
            headers = {"Authorization": f"Bearer {token}", "X-Organization-Id": org}
            assert (await db_client.get(path, headers=headers)).status_code == 401


@requires_db
async def test_same_org_membership_dedupe_and_stale_header(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    other = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    await _add_membership(
        db_engine,
        user_id=actor.user_id,
        organization_id=actor.organization_id,
        role_code=RoleCode.REGISTRAR,
    )
    await _add_membership(
        db_engine,
        user_id=actor.user_id,
        organization_id=other.organization_id,
        role_code=RoleCode.ORG_ADMIN,
    )
    listed = await db_client.get(
        _ORGS,
        headers={**_auth(actor.token), "X-Organization-Id": str(actor.organization_id)},
    )
    assert listed.status_code == 200
    orgs = listed.json()["organizations"]
    ids = _ids(orgs, "organization_id")
    assert ids.count(str(actor.organization_id)) == 1
    assert set(ids) == {str(actor.organization_id), str(other.organization_id)}
    home = next(item for item in orgs if item["organization_id"] == str(actor.organization_id))
    assert home["role_codes"] == [RoleCode.CLINICIAN, RoleCode.REGISTRAR]


@requires_db
async def test_organization_name_tie_is_deterministic(db_client, db_engine) -> None:
    first = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    second = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    await _set_org_name(db_engine, first.organization_id, "Same Display Hospital")
    await _set_org_name(db_engine, second.organization_id, "Same Display Hospital")
    await _add_membership(
        db_engine,
        user_id=first.user_id,
        organization_id=second.organization_id,
        role_code=RoleCode.AUDITOR,
    )
    actor = _as_actor(first)
    first_list = (await db_client.get(_ORGS, headers=_auth(actor.token))).json()["organizations"]
    second_list = (await db_client.get(_ORGS, headers=_auth(actor.token))).json()["organizations"]
    assert first_list == second_list
    keys = [(item["name"].lower(), item["code"], item["organization_id"]) for item in first_list]
    assert keys == sorted(keys)
    assert len(first_list) == 2


@requires_db
async def test_platform_only_provisioned_is_not_tenant_authority(db_client, db_engine) -> None:
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    listed = (await db_client.get(_ORGS, headers=_auth(platform.token))).json()
    assert listed["provisioned"] is True
    assert listed["organizations"] == []
    assert listed["user"]["subject"] == platform.subject
    ctx = await db_client.get(_CONTEXT, headers=_org_headers(platform, platform.organization_id))
    _conceal(ctx)


@requires_db
async def test_context_requires_org_and_concealment_alignment(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    foreign = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    missing = await db_client.get(_CONTEXT, headers=_auth(actor.token))
    assert missing.status_code == 422
    assert "CLINICIAN" not in str(missing.json())
    assert str(actor.organization_id) not in str(missing.json().get("error", missing.json()))

    unknown = uuid4()
    concealed = (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, unknown)),
        await db_client.get(_accessible(unknown), headers=_org_headers(actor, unknown)),
        await db_client.get(_CONTEXT, headers=_org_headers(actor, foreign.organization_id)),
        await db_client.get(
            _accessible(foreign.organization_id),
            headers=_org_headers(actor, foreign.organization_id),
        ),
    )
    for response in concealed:
        _conceal(response)
    missing_header = await db_client.get(
        _accessible(actor.organization_id),
        headers=_auth(actor.token),
    )
    assert missing_header.status_code == 422


@requires_db
async def test_permission_equivalence_matches_enforcement(db_client, db_engine) -> None:
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

    ctx_a = (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, hospital_a.organization_id))
    ).json()
    ctx_b = (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, hospital_b.organization_id))
    ).json()
    assert ctx_a["effective_permissions"] == sorted(ROLE_PERMISSIONS[RoleCode.CLINICIAN])
    assert ctx_b["effective_permissions"] == sorted(ROLE_PERMISSIONS[RoleCode.ORG_ADMIN])
    assert Permission.CLINICAL_CONDITION_CREATE in ctx_a["effective_permissions"]
    assert Permission.CLINICAL_CONDITION_CREATE not in ctx_b["effective_permissions"]
    assert Permission.ORG_FACILITY_CREATE in ctx_b["effective_permissions"]
    assert Permission.ORG_FACILITY_CREATE not in ctx_a["effective_permissions"]
    assert ctx_a["role_codes"] == [RoleCode.CLINICIAN]
    assert ctx_b["role_codes"] == [RoleCode.ORG_ADMIN]
    assert ctx_a["organization"]["organization_id"] == str(hospital_a.organization_id)
    assert str(hospital_b.organization_id) not in str(ctx_a)
    assert Permission.ORG_FACILITY_CREATE not in str(ctx_a["effective_permissions"])
    assert ctx_a["effective_permissions"] == sorted(set(ctx_a["effective_permissions"]))
    assert (
        ctx_a["effective_permissions"]
        == (
            await db_client.get(_CONTEXT, headers=_org_headers(actor, hospital_a.organization_id))
        ).json()["effective_permissions"]
    )

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
    facility_b = await db_client.post(
        f"/api/v1/organizations/{hospital_b.organization_id}/facilities",
        headers=_staff_headers(actor, hospital_b.organization_id, "ADMINISTRATION"),
        json=_facility_payload("Admin Site"),
    )
    facility_a = await db_client.post(
        f"/api/v1/organizations/{hospital_a.organization_id}/facilities",
        headers=_staff_headers(actor, hospital_a.organization_id, "ADMINISTRATION"),
        json=_facility_payload("Clinician Site"),
    )
    assert facility_b.status_code in {200, 201}
    assert facility_a.status_code == 403


@requires_db
async def test_staff_roles_can_read_accessible_facilities(db_client, db_engine) -> None:
    roles = (
        RoleCode.CLINICIAN,
        RoleCode.REGISTRAR,
        RoleCode.ORG_ADMIN,
        RoleCode.AUDITOR,
        RoleCode.IDENTITY_OFFICER,
    )
    for role in roles:
        actor = await seed_actor(db_engine, role_code=role)
        await _add_facility(db_engine, actor.organization_id, f"{role} Site")
        response = await db_client.get(
            _accessible(actor.organization_id),
            headers=_org_headers(actor, actor.organization_id),
        )
        assert response.status_code == 200, role
        assert response.json()["facility_scope"] == "ALL_IN_ORGANIZATION"
        assert len(response.json()["facilities"]) == 1


@requires_db
async def test_work_facility_required_and_scope_consistency(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    site_a = await _add_facility(db_engine, actor.organization_id, "Alpha")
    site_b = await _add_facility(db_engine, actor.organization_id, "Beta")
    inactive = new_id()
    async with db_engine.begin() as connection:
        await connection.execute(
            FacilityModel.__table__.insert().values(
                id=inactive,
                organization_id=actor.organization_id,
                name="Inactive",
                code=f"I{inactive.hex[:10].upper()}",
                facility_type=FacilityType.HOSPITAL_SITE,
                status=FacilityStatus.INACTIVE,
            )
        )

    ctx = (await db_client.get(_CONTEXT, headers=_org_headers(actor, actor.organization_id))).json()
    fac = (
        await db_client.get(
            _accessible(actor.organization_id),
            headers=_org_headers(actor, actor.organization_id),
        )
    ).json()
    assert ctx["facility_scope"] == fac["facility_scope"] == "ALL_IN_ORGANIZATION"
    assert ctx["work_facility_required"] is False
    assert _ids(fac["facilities"], "id") == [str(site_a), str(site_b)]

    await _bind_membership_facility(db_engine, actor.user_id, actor.organization_id, site_a)
    ctx_one = (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, actor.organization_id))
    ).json()
    fac_one = (
        await db_client.get(
            _accessible(actor.organization_id),
            headers=_org_headers(actor, actor.organization_id),
        )
    ).json()
    assert ctx_one["facility_scope"] == fac_one["facility_scope"] == "EXPLICIT"
    assert ctx_one["work_facility_required"] is True
    assert _ids(fac_one["facilities"], "id") == [str(site_a)]

    await _add_membership(
        db_engine,
        user_id=actor.user_id,
        organization_id=actor.organization_id,
        role_code=RoleCode.REGISTRAR,
        facility_id=inactive,
    )
    ctx_zero_active = (
        await db_client.get(_CONTEXT, headers=_org_headers(actor, actor.organization_id))
    ).json()
    fac_zero_active = (
        await db_client.get(
            _accessible(actor.organization_id),
            headers=_org_headers(actor, actor.organization_id),
        )
    ).json()
    assert ctx_zero_active["facility_scope"] == "EXPLICIT"
    assert ctx_zero_active["work_facility_required"] is True
    assert _ids(fac_zero_active["facilities"], "id") == [str(site_a)]
    assert str(inactive) not in _ids(fac_zero_active["facilities"], "id")


@requires_db
async def test_corrupt_foreign_facility_id_and_revoked_do_not_leak(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    site_a1 = await _add_facility(db_engine, hospital_a.organization_id, "A1")
    site_a2 = await _add_facility(db_engine, hospital_a.organization_id, "A2")
    site_b = await _add_facility(db_engine, hospital_b.organization_id, "B1")
    await _set_membership_facility(
        db_engine,
        hospital_a.user_id,
        hospital_a.organization_id,
        RoleCode.CLINICIAN,
        site_a1,
    )
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_a.organization_id,
        role_code=RoleCode.REGISTRAR,
        facility_id=site_b,
    )
    listed = await db_client.get(
        _accessible(hospital_a.organization_id),
        headers=_org_headers(hospital_a, hospital_a.organization_id),
    )
    assert listed.status_code == 200
    assert listed.json()["facility_scope"] == "EXPLICIT"
    assert _ids(listed.json()["facilities"], "id") == [str(site_a1)]
    assert str(site_b) not in _ids(listed.json()["facilities"], "id")
    assert str(site_a2) not in _ids(listed.json()["facilities"], "id")

    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_a.organization_id,
        role_code=RoleCode.AUDITOR,
        facility_id=site_a2,
    )
    await _revoke_role_membership(
        db_engine, hospital_a.user_id, hospital_a.organization_id, RoleCode.AUDITOR
    )
    after_revoke = await db_client.get(
        _accessible(hospital_a.organization_id),
        headers=_org_headers(hospital_a, hospital_a.organization_id),
    )
    assert _ids(after_revoke.json()["facilities"], "id") == [str(site_a1)]
    assert str(site_a2) not in _ids(after_revoke.json()["facilities"], "id")


@requires_db
async def test_header_path_mismatch_and_switch_isolation(db_client, db_engine) -> None:
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
    mismatch_ab = await db_client.get(
        _accessible(hospital_b.organization_id),
        headers=_org_headers(actor, hospital_a.organization_id),
    )
    mismatch_ba = await db_client.get(
        _accessible(hospital_a.organization_id),
        headers=_org_headers(actor, hospital_b.organization_id),
    )
    _conceal(mismatch_ab)
    _conceal(mismatch_ba)
    assert str(site_a) not in str(mismatch_ab.json())
    assert str(site_b) not in str(mismatch_ba.json())

    for _ in range(3):
        ctx_a = (
            await db_client.get(_CONTEXT, headers=_org_headers(actor, hospital_a.organization_id))
        ).json()
        fac_a = (
            await db_client.get(
                _accessible(hospital_a.organization_id),
                headers=_org_headers(actor, hospital_a.organization_id),
            )
        ).json()
        ctx_b = (
            await db_client.get(_CONTEXT, headers=_org_headers(actor, hospital_b.organization_id))
        ).json()
        fac_b = (
            await db_client.get(
                _accessible(hospital_b.organization_id),
                headers=_org_headers(actor, hospital_b.organization_id),
            )
        ).json()
        assert ctx_a["facility_scope"] == fac_a["facility_scope"] == "EXPLICIT"
        assert ctx_b["facility_scope"] == fac_b["facility_scope"] == "EXPLICIT"
        assert _ids(fac_a["facilities"], "id") == [str(site_a)]
        assert _ids(fac_b["facilities"], "id") == [str(site_b)]
        assert ctx_a["role_codes"] == [RoleCode.CLINICIAN]
        assert ctx_b["role_codes"] == [RoleCode.REGISTRAR]


@requires_db
async def test_concurrent_context_and_organizations_are_request_local(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    await _add_membership(
        db_engine,
        user_id=hospital_a.user_id,
        organization_id=hospital_b.organization_id,
        role_code=RoleCode.ORG_ADMIN,
    )
    actor = _as_actor(hospital_a)
    ctx_a, ctx_b, listed = await asyncio.gather(
        db_client.get(_CONTEXT, headers=_org_headers(actor, hospital_a.organization_id)),
        db_client.get(_CONTEXT, headers=_org_headers(actor, hospital_b.organization_id)),
        db_client.get(_ORGS, headers=_auth(actor.token)),
    )
    assert ctx_a.status_code == ctx_b.status_code == listed.status_code == 200
    body_a, body_b = ctx_a.json(), ctx_b.json()
    assert body_a["role_codes"] == [RoleCode.CLINICIAN]
    assert body_b["role_codes"] == [RoleCode.ORG_ADMIN]
    assert Permission.CLINICAL_CONDITION_CREATE in body_a["effective_permissions"]
    assert Permission.CLINICAL_CONDITION_CREATE not in body_b["effective_permissions"]
    assert set(_ids(listed.json()["organizations"], "organization_id")) == {
        str(hospital_a.organization_id),
        str(hospital_b.organization_id),
    }


@requires_db
async def test_purpose_exempt_does_not_expand_authority(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    foreign = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    headers = _org_headers(actor, actor.organization_id)
    none = await db_client.get(_CONTEXT, headers=headers)
    valid = await db_client.get(_CONTEXT, headers={**headers, "X-Purpose": "TREATMENT"})
    invalid = await db_client.get(_CONTEXT, headers={**headers, "X-Purpose": "not-a-purpose"})
    assert none.status_code == valid.status_code == invalid.status_code == 200
    assert none.json()["effective_permissions"] == valid.json()["effective_permissions"]
    assert invalid.json()["effective_permissions"] == none.json()["effective_permissions"]
    spoof = await db_client.get(
        _CONTEXT,
        headers={
            **_org_headers(actor, foreign.organization_id),
            "X-Purpose": "ADMINISTRATION",
        },
    )
    _conceal(spoof)
    orgs = await db_client.get(_ORGS, headers={**_auth(actor.token), "X-Purpose": "not-a-purpose"})
    assert orgs.status_code == 200


@requires_db
async def test_success_reads_do_not_audit_or_write_provenance(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    before_audit = await _count(db_engine, "SELECT count(*) FROM audit_events")
    before_prov = await _provenance_count(db_engine)
    listed = await db_client.get(_ORGS, headers=_auth(actor.token))
    ctx = await db_client.get(_CONTEXT, headers=_org_headers(actor, actor.organization_id))
    fac = await db_client.get(
        _accessible(actor.organization_id),
        headers=_org_headers(actor, actor.organization_id),
    )
    me = await db_client.get("/api/v1/iam/users/me", headers=_auth(actor.token))
    after_audit = await _count(db_engine, "SELECT count(*) FROM audit_events")
    after_prov = await _provenance_count(db_engine)
    assert listed.status_code == ctx.status_code == fac.status_code == me.status_code == 200
    assert after_audit == before_audit
    assert after_prov == before_prov
    assert set(me.json()) == {
        "provisioned",
        "id",
        "subject",
        "display_name",
        "roles",
        "permissions",
    }
    for payload in (listed.json(), ctx.json(), fac.json()):
        _assert_minimized(payload)
    assert fac.json()["facilities"] == [] or "address_text" not in str(fac.json())
    invalid_uuid = await db_client.get(
        _CONTEXT, headers={**_auth(actor.token), "X-Organization-Id": "not-a-uuid"}
    )
    assert invalid_uuid.status_code == 422
    assert "traceback" not in str(invalid_uuid.json()).lower()


@requires_db
async def test_bounded_queries_for_many_memberships_and_facilities(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    for index in range(8):
        other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
        await _add_membership(
            db_engine,
            user_id=actor.user_id,
            organization_id=other.organization_id,
            role_code=RoleCode.AUDITOR,
        )
        await _add_facility(db_engine, actor.organization_id, f"Home {index:02d}")
    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany) -> None:
        del conn, cursor, parameters, context, executemany
        statements.append(statement)

    event.listen(db_engine.sync_engine, "before_cursor_execute", _capture)
    try:
        listed = await db_client.get(_ORGS, headers=_auth(actor.token))
        ctx = await db_client.get(_CONTEXT, headers=_org_headers(actor, actor.organization_id))
        fac = await db_client.get(
            _accessible(actor.organization_id),
            headers=_org_headers(actor, actor.organization_id),
        )
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", _capture)
    assert listed.status_code == ctx.status_code == fac.status_code == 200
    assert len(listed.json()["organizations"]) == 9
    keys = [
        (item["name"].lower(), item["code"], item["organization_id"])
        for item in listed.json()["organizations"]
    ]
    assert keys == sorted(keys)
    facility_selects = [
        item
        for item in statements
        if "from facilities" in item.lower() and item.lstrip().lower().startswith("select")
    ]
    org_selects = [
        item
        for item in statements
        if "from organizations" in item.lower() and item.lstrip().lower().startswith("select")
    ]
    assert len(facility_selects) <= 2
    assert len(org_selects) <= 4
    assert fac.json()["facility_scope"] == "ALL_IN_ORGANIZATION"
    assert len(fac.json()["facilities"]) == 8
    names = [item["name"] for item in fac.json()["facilities"]]
    assert names == sorted(names)
