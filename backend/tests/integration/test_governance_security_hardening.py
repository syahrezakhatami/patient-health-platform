"""Adversarial security tests for Organization Governance Profile."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.governance.domain.enums import (
    FeatureActivationState,
    GovernanceDenialReason,
    ProviderCapabilityState,
)
from app.modules.governance.domain.policy_schema import GovernancePolicyDocumentV1
from app.modules.governance.domain.transitions import (
    validate_activation_transition,
    validate_provider_transition,
)
from app.shared.types.ids import new_id
from sqlalchemy import text
from tests.conftest import mint_token
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.governance_helpers import (
    governance_headers,
    insert_test_provider_capability,
    seed_governance_actor,
)

pytestmark = [pytest.mark.integration, requires_db]

_FORBIDDEN_EFFECTIVE_CONTEXT_KEYS = frozenset(
    {
        "denial_reason",
        "decision_by_name",
        "recorded_by_user_id",
        "artifact_reference",
        "dpa",
        "gate_state",
        "approval_evidence",
        "plan",
        "entitlement",
        "waiver",
        "internal",
    }
)


def _org_code(prefix: str) -> str:
    return f"{prefix}{new_id().hex[:6]}".upper()


async def _org_admin(db_engine, prefix: str):
    return await seed_actor(
        db_engine,
        role_code=RoleCode.ORG_ADMIN,
        org_code=_org_code(prefix),
    )


def _policy() -> dict[str, object]:
    return GovernancePolicyDocumentV1().model_dump(mode="json")


def _approval_body(feature_id: str = "test_governed_feature") -> dict[str, object]:
    return {
        "feature_id": feature_id,
        "provider_feature_version": "1.0.0",
        "approval_type": "CLINICAL",
        "scope": "SITE",
        "decision_by_name": "Dr Example",
        "approval_date": date.today().isoformat(),
    }


def _collect_keys(value: object, *, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            full = f"{prefix}.{key}" if prefix else str(key)
            keys.add(full.lower())
            keys |= _collect_keys(nested, prefix=full)
    elif isinstance(value, list):
        for item in value:
            keys |= _collect_keys(item, prefix=prefix)
    return keys


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path_template", "json_body", "needs_idempotency"),
    [
        ("get", "/api/v1/organizations/{org_b}/governance/profile", None, False),
        (
            "post",
            "/api/v1/organizations/{org_b}/governance/profile/versions",
            {
                "policy_document": _policy(),
                "effective_at": datetime.now(UTC).isoformat(),
                "reason": "Cross-org attack",
            },
            True,
        ),
        (
            "post",
            "/api/v1/organizations/{org_b}/governance/approvals",
            _approval_body(),
            True,
        ),
        (
            "post",
            "/api/v1/organizations/{org_b}/governance/features/test_feat/transition",
            {"target_state": "PENDING_APPROVAL"},
            False,
        ),
        (
            "put",
            "/api/v1/organizations/{org_b}/governance/deployment-gates/DPA",
            {"gate_state": "SATISFIED"},
            False,
        ),
        ("get", "/api/v1/organizations/{org_b}/governance/effective-context", None, False),
    ],
)
async def test_cross_org_idor_matrix(
    db_client,
    db_engine,
    method: str,
    path_template: str,
    json_body: dict[str, object] | None,
    needs_idempotency: bool,
) -> None:
    actor_a = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN, org_code=_org_code("SEC_A"))
    actor_b = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN, org_code=_org_code("SEC_B"))
    path = path_template.format(org_b=actor_b.organization_id)
    headers = governance_headers(
        actor_a,
        idempotency_key=f"sec-idor-{new_id().hex[:8]}" if needs_idempotency else None,
    )
    response = await db_client.request(method, path, headers=headers, json=json_body)
    assert response.status_code in {403, 404}
    if response.status_code == 200:
        payload = response.text
        assert str(actor_b.organization_id) not in payload or "organization_id" not in payload


@pytest.mark.asyncio
async def test_cross_org_publish_foreign_version_id(db_client, db_engine) -> None:
    org_a = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN, org_code=_org_code("SECPA"))
    org_b = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN, org_code=_org_code("SECPB"))
    create = await db_client.post(
        f"/api/v1/organizations/{org_a.organization_id}/governance/profile/versions",
        json={
            "policy_document": _policy(),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Org A version",
        },
        headers=governance_headers(org_a, idempotency_key=f"sec-pub-a-{new_id().hex[:8]}"),
    )
    assert create.status_code == 200
    version_id = create.json()["id"]
    publish = await db_client.post(
        (
            f"/api/v1/organizations/{org_b.organization_id}/governance/"
            f"profile/versions/{version_id}/publish"
        ),
        headers=governance_headers(org_b, idempotency_key=f"sec-pub-b-{new_id().hex[:8]}"),
    )
    assert publish.status_code in {403, 404}


@pytest.mark.asyncio
async def test_valid_token_without_org_membership_concealed(db_client, db_engine) -> None:
    outsider = await _org_admin(db_engine, "SECOUT")
    target = await _org_admin(db_engine, "SECTGT")
    response = await db_client.get(
        f"/api/v1/organizations/{target.organization_id}/governance/effective-context",
        headers={
            "Authorization": f"Bearer {outsider.token}",
            "X-Organization-Id": str(target.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert response.status_code in {403, 404}


@pytest.mark.asyncio
async def test_platform_token_rejected_on_org_governance(db_client, db_engine, db_settings) -> None:
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    org = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN, org_code=_org_code("SECPLT"))
    token = mint_token(sub=platform.subject, aud=db_settings.auth_platform_audience)
    response = await db_client.get(
        f"/api/v1/organizations/{org.organization_id}/governance/profile",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": str(org.organization_id),
            "X-Purpose": "platform_governance",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_staff_token_with_provider_permission_rejected_on_platform_api(
    db_client, db_engine, db_settings
) -> None:
    actor = await seed_governance_actor(
        db_engine,
        permissions=frozenset({Permission.GOVERNANCE_PROVIDER_MANAGE}),
        org_code=_org_code("SECSTF"),
    )
    response = await db_client.get(
        "/api/v1/platform/governance/capabilities",
        headers=governance_headers(actor),
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_effective_context_oracle_safe_keys(db_client, db_engine) -> None:
    feature_id = f"test_oracle_{new_id().hex[:8]}"
    await insert_test_provider_capability(
        db_engine,
        feature_id=feature_id,
        governance_required=True,
    )
    org_admin = await _org_admin(db_engine, "SECORC")
    response = await db_client.get(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/effective-context",
        headers=governance_headers(org_admin, purpose="TREATMENT"),
    )
    assert response.status_code == 200
    keys = _collect_keys(response.json())
    assert keys & _FORBIDDEN_EFFECTIVE_CONTEXT_KEYS == set()
    for item in response.json().get("governed_features", []):
        assert set(item.keys()) <= {"feature_id", "available", "feature_version"}
        assert "denial" not in str(item).lower()


@pytest.mark.asyncio
async def test_policy_extra_fields_rejected(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "SECPOL")
    policy = _policy()
    policy["allow_all"] = True
    response = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/profile/versions",
        json={
            "policy_document": policy,
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Policy attack",
        },
        headers=governance_headers(org_admin, idempotency_key=f"sec-pol-{new_id().hex[:8]}"),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_policy_enum_tampering_rejected(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "SECENU")
    policy = _policy()
    policy["encounter_status_policy"]["planned"] = "ALLOW_ALL"
    response = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/profile/versions",
        json={
            "policy_document": policy,
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Enum attack",
        },
        headers=governance_headers(org_admin, idempotency_key=f"sec-enum-{new_id().hex[:8]}"),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_request_extra_fields_forbidden(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "SECEXT")
    response = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/profile/versions",
        json={
            "policy_document": _policy(),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Extra field",
            "approved": True,
            "organization_id": str(uuid4()),
        },
        headers=governance_headers(org_admin, idempotency_key=f"sec-ext-{new_id().hex[:8]}"),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_gate_type_spoofing_rejected(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "SECGT")
    response = await db_client.put(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/deployment-gates/SKIP_DPA",
        json={"gate_state": "SATISFIED"},
        headers=governance_headers(org_admin),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_feature_id_injection_safe(db_client, db_engine) -> None:
    actor = await seed_governance_actor(
        db_engine,
        permissions=frozenset({Permission.GOVERNANCE_FEATURE_ACTIVATE}),
        org_code=_org_code("SECINJ"),
    )
    malicious = "test'; DROP TABLE provider_capabilities;--"
    response = await db_client.post(
        (
            f"/api/v1/organizations/{actor.organization_id}/governance/"
            f"features/{malicious}/transition"
        ),
        json={"target_state": "PENDING_APPROVAL"},
        headers=governance_headers(actor),
    )
    assert response.status_code in {404, 409, 422}
    async with db_engine.connect() as connection:
        count = (
            await connection.execute(text("SELECT COUNT(*) FROM provider_capabilities"))
        ).scalar_one()
    assert count >= 0


@pytest.mark.asyncio
async def test_idempotency_cross_actor_no_collision(db_client, db_engine) -> None:
    actor_a = await seed_governance_actor(
        db_engine,
        permissions=frozenset({Permission.GOVERNANCE_PROFILE_MANAGE}),
        org_code=_org_code("SECIDA"),
    )
    actor_b = await seed_governance_actor(
        db_engine,
        permissions=frozenset({Permission.GOVERNANCE_PROFILE_MANAGE}),
        org_code=_org_code("SECIDB"),
    )
    body = {
        "policy_document": _policy(),
        "effective_at": datetime.now(UTC).isoformat(),
        "reason": "Cross actor",
    }
    key = f"shared-key-{new_id().hex[:8]}"
    first = await db_client.post(
        f"/api/v1/organizations/{actor_a.organization_id}/governance/profile/versions",
        json=body,
        headers=governance_headers(actor_a, idempotency_key=key),
    )
    second = await db_client.post(
        f"/api/v1/organizations/{actor_b.organization_id}/governance/profile/versions",
        json=body,
        headers=governance_headers(actor_b, idempotency_key=key),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_idempotency_cross_org_same_actor(db_client, db_engine) -> None:
    user_id = new_id()
    subject = f"user-{new_id()}"
    org_a_id = new_id()
    org_b_id = new_id()
    role_id = new_id()
    from app.modules.iam.domain.enums import MembershipStatus, UserStatus
    from app.modules.iam.infrastructure.models import (
        OrganizationMembershipModel,
        RoleModel,
        UserModel,
    )
    from app.modules.organization.domain.enums import OrganizationStatus, OrganizationType
    from app.modules.organization.infrastructure.models import OrganizationModel

    org_a_code = _org_code("SECMOA")
    org_b_code = _org_code("SECMOB")
    async with db_engine.begin() as connection:
        for org_id, code in ((org_a_id, org_a_code), (org_b_id, org_b_code)):
            await connection.execute(
                OrganizationModel.__table__.insert().values(
                    id=org_id,
                    name=f"Org {code}",
                    code=code,
                    organization_type=OrganizationType.HOSPITAL,
                    status=OrganizationStatus.ACTIVE,
                )
            )
        perm_rows = (
            await connection.execute(
                text(
                    """
                    SELECT id FROM permissions
                    WHERE code IN ('governance.profile.manage', 'governance.profile.read')
                    """
                )
            )
        ).fetchall()
        await connection.execute(
            RoleModel.__table__.insert().values(
                id=role_id,
                code=f"GOV_MULTI_{new_id().hex[:6]}",
                name="Multi org governance",
            )
        )
        for (perm_id,) in perm_rows:
            await connection.execute(
                text(
                    """
                    INSERT INTO role_permissions (id, role_id, permission_id)
                    VALUES (:id, :role_id, :permission_id)
                    """
                ),
                {"id": new_id(), "role_id": role_id, "permission_id": perm_id},
            )
        await connection.execute(
            UserModel.__table__.insert().values(
                id=user_id,
                subject=subject,
                display_name=subject,
                status=UserStatus.ACTIVE,
            )
        )
        for org_id in (org_a_id, org_b_id):
            await connection.execute(
                OrganizationMembershipModel.__table__.insert().values(
                    id=new_id(),
                    user_id=user_id,
                    organization_id=org_id,
                    facility_id=None,
                    role_id=role_id,
                    status=MembershipStatus.ACTIVE,
                )
            )
    token = mint_token(sub=subject)
    body = {
        "policy_document": _policy(),
        "effective_at": datetime.now(UTC).isoformat(),
        "reason": "Cross org key",
    }
    key = f"cross-org-{new_id().hex[:8]}"
    first = await db_client.post(
        f"/api/v1/organizations/{org_a_id}/governance/profile/versions",
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": str(org_a_id),
            "X-Purpose": "governance_administration",
            "Idempotency-Key": key,
        },
    )
    second = await db_client.post(
        f"/api/v1/organizations/{org_b_id}/governance/profile/versions",
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": str(org_b_id),
            "X-Purpose": "governance_administration",
            "Idempotency-Key": key,
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_idempotency_cross_operation_no_replay(db_client, db_engine) -> None:
    actor = await seed_governance_actor(
        db_engine,
        permissions=frozenset(
            {Permission.GOVERNANCE_PROFILE_MANAGE, Permission.GOVERNANCE_APPROVAL_RECORD}
        ),
        org_code=_org_code("SECOP"),
    )
    key = f"cross-op-{new_id().hex[:8]}"
    profile = await db_client.post(
        f"/api/v1/organizations/{actor.organization_id}/governance/profile/versions",
        json={
            "policy_document": _policy(),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Operation one",
        },
        headers=governance_headers(actor, idempotency_key=key),
    )
    approval = await db_client.post(
        f"/api/v1/organizations/{actor.organization_id}/governance/approvals",
        json=_approval_body(),
        headers=governance_headers(actor, idempotency_key=key),
    )
    assert profile.status_code == 200
    assert approval.status_code == 200


@pytest.mark.asyncio
async def test_idempotency_replay_requires_current_permission(db_client, db_engine) -> None:
    actor = await seed_governance_actor(
        db_engine,
        permissions=frozenset({Permission.GOVERNANCE_PROFILE_MANAGE}),
        org_code=_org_code("SECREP"),
    )
    key = f"replay-auth-{new_id().hex[:8]}"
    body = {
        "policy_document": _policy(),
        "effective_at": datetime.now(UTC).isoformat(),
        "reason": "Replay auth",
    }
    first = await db_client.post(
        f"/api/v1/organizations/{actor.organization_id}/governance/profile/versions",
        json=body,
        headers=governance_headers(actor, idempotency_key=key),
    )
    assert first.status_code == 200
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                """
                DELETE FROM role_permissions rp
                USING roles r, permissions p
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
                  AND r.id IN (
                    SELECT role_id FROM organization_memberships
                    WHERE user_id = :user_id
                  )
                  AND p.code = 'governance.profile.manage'
                """
            ),
            {"user_id": actor.user_id},
        )
    retry = await db_client.post(
        f"/api/v1/organizations/{actor.organization_id}/governance/profile/versions",
        json=body,
        headers=governance_headers(actor, idempotency_key=key),
    )
    assert retry.status_code == 403


@pytest.mark.asyncio
async def test_idempotency_fingerprint_conflict(db_client, db_engine) -> None:
    actor = await seed_governance_actor(
        db_engine,
        permissions=frozenset({Permission.GOVERNANCE_PROFILE_MANAGE}),
        org_code=_org_code("SECCON"),
    )
    key = f"fp-conflict-{new_id().hex[:8]}"
    first = await db_client.post(
        f"/api/v1/organizations/{actor.organization_id}/governance/profile/versions",
        json={
            "policy_document": _policy(),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "One",
        },
        headers=governance_headers(actor, idempotency_key=key),
    )
    second = await db_client.post(
        f"/api/v1/organizations/{actor.organization_id}/governance/profile/versions",
        json={
            "policy_document": _policy(),
            "effective_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "reason": "Two",
        },
        headers=governance_headers(actor, idempotency_key=key),
    )
    assert first.status_code == 200
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_synthetic_provider_suspend_denies_resolution(db_engine) -> None:
    from app.db.session import create_session_factory
    from app.modules.audit.infrastructure.sqlalchemy_sink import SqlAlchemyAuditSink
    from app.modules.authorization.application.product_access_pdp import ProductAccessPDP
    from app.modules.governance.application.services import GovernanceService

    feature_id = f"test_kill_{new_id().hex[:8]}"
    await insert_test_provider_capability(
        db_engine,
        feature_id=feature_id,
        governance_required=False,
        provider_state=ProviderCapabilityState.SUSPENDED,
    )
    org_id = new_id()
    session_factory = create_session_factory(db_engine)
    async with session_factory() as session:
        service = GovernanceService(session, ProductAccessPDP(), SqlAlchemyAuditSink(session))
        result = await service.resolve_feature(org_id, feature_id)
    assert result.denial_reason == GovernanceDenialReason.DENIED_PROVIDER


@pytest.mark.asyncio
async def test_missing_provider_row_no_global_deny(db_engine) -> None:
    from app.db.session import create_session_factory
    from app.modules.audit.infrastructure.sqlalchemy_sink import SqlAlchemyAuditSink
    from app.modules.authorization.application.product_access_pdp import ProductAccessPDP
    from app.modules.governance.application.services import GovernanceService

    session_factory = create_session_factory(db_engine)
    async with session_factory() as session:
        service = GovernanceService(session, ProductAccessPDP(), SqlAlchemyAuditSink(session))
        result = await service.resolve_feature(new_id(), "clinical_note_write")
    assert result.registered is False
    assert result.denial_reason == GovernanceDenialReason.NOT_REGISTERED


@pytest.mark.asyncio
async def test_governance_required_missing_profile_fail_closed(db_engine) -> None:
    from app.db.session import create_session_factory
    from app.modules.audit.infrastructure.sqlalchemy_sink import SqlAlchemyAuditSink
    from app.modules.authorization.application.product_access_pdp import ProductAccessPDP
    from app.modules.governance.application.services import GovernanceService

    feature_id = f"test_closed_{new_id().hex[:8]}"
    await insert_test_provider_capability(
        db_engine,
        feature_id=feature_id,
        governance_required=True,
    )
    org_admin = await _org_admin(db_engine, "SECFCL")
    session_factory = create_session_factory(db_engine)
    async with session_factory() as session:
        service = GovernanceService(session, ProductAccessPDP(), SqlAlchemyAuditSink(session))
        result = await service.resolve_feature(org_admin.organization_id, feature_id)
    assert result.available is False
    assert result.denial_reason == GovernanceDenialReason.DENIED_SITE_ACTIVATION


@pytest.mark.asyncio
async def test_app_dml_cannot_update_idempotency(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "SECDML")
    create = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/profile/versions",
        json={
            "policy_document": _policy(),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Idempotency privilege test",
        },
        headers=governance_headers(org_admin, idempotency_key=f"sec-dml-{new_id().hex[:8]}"),
    )
    assert create.status_code == 200
    async with db_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT id FROM governance_admin_idempotency
                    WHERE organization_id = :org_id
                    LIMIT 1
                    """
                ),
                {"org_id": org_admin.organization_id},
            )
        ).first()
    assert row is not None
    with pytest.raises(Exception, match="permission denied|immutable"):
        async with db_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE governance_admin_idempotency
                    SET request_fingerprint = repeat('a', 64)
                    WHERE id = :id
                    """
                ),
                {"id": row[0]},
            )


@pytest.mark.asyncio
async def test_org_admin_default_permissions(db_engine) -> None:
    async with db_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT p.code FROM role_permissions rp
                    JOIN roles r ON r.id = rp.role_id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE r.code = 'ORG_ADMIN' AND p.code LIKE 'governance.%'
                    ORDER BY p.code
                    """
                )
            )
        ).fetchall()
    codes = {row[0] for row in rows}
    assert codes == {"governance.profile.manage", "governance.profile.read"}


@pytest.mark.asyncio
async def test_clinician_has_no_governance_permissions(db_engine) -> None:
    async with db_engine.connect() as connection:
        count = (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*) FROM role_permissions rp
                    JOIN roles r ON r.id = rp.role_id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE r.code = 'CLINICIAN' AND p.code LIKE 'governance.%'
                    """
                )
            )
        ).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_auditor_has_no_governance_permissions(db_engine) -> None:
    async with db_engine.connect() as connection:
        count = (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*) FROM role_permissions rp
                    JOIN roles r ON r.id = rp.role_id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE r.code = 'AUDITOR' AND p.code LIKE 'governance.%'
                    """
                )
            )
        ).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_production_registry_empty(db_engine) -> None:
    async with db_engine.connect() as connection:
        count = (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*) FROM provider_capabilities
                    WHERE feature_id IN ('clinical_note_write', 'manual_vital_signs_write')
                    """
                )
            )
        ).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_concurrent_same_key_profile_create(db_client, db_engine) -> None:
    actor = await seed_governance_actor(
        db_engine,
        permissions=frozenset({Permission.GOVERNANCE_PROFILE_MANAGE}),
        org_code=_org_code("SECCNC"),
    )
    body = {
        "policy_document": _policy(),
        "effective_at": datetime.now(UTC).isoformat(),
        "reason": "Concurrent security",
    }
    key = f"sec-concurrent-{new_id().hex[:8]}"
    headers = governance_headers(actor, idempotency_key=key)

    async def _post() -> dict[str, object]:
        response = await db_client.post(
            f"/api/v1/organizations/{actor.organization_id}/governance/profile/versions",
            json=body,
            headers=headers,
        )
        return {"status": response.status_code, "id": response.json().get("id")}

    results = await asyncio.gather(_post(), _post())
    assert all(item["status"] == 200 for item in results)
    assert results[0]["id"] == results[1]["id"]


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ProviderCapabilityState.RETIRED, ProviderCapabilityState.AVAILABLE),
        (ProviderCapabilityState.RETIRED, ProviderCapabilityState.SUSPENDED),
        (ProviderCapabilityState.SUSPENDED, ProviderCapabilityState.RETIRED),
        (ProviderCapabilityState.AVAILABLE, ProviderCapabilityState.AVAILABLE),
    ],
)
def test_provider_illegal_or_noop_transitions(
    current: ProviderCapabilityState,
    target: ProviderCapabilityState,
) -> None:
    if current == target:
        assert validate_provider_transition(current, target) is False
        return
    if current == ProviderCapabilityState.RETIRED:
        with pytest.raises(AppError):
            validate_provider_transition(current, target)
        return
    result = validate_provider_transition(current, target)
    assert isinstance(result, bool)


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (None, FeatureActivationState.ACTIVE, False),
        (FeatureActivationState.RETIRED, FeatureActivationState.ACTIVE, False),
        (FeatureActivationState.PENDING_APPROVAL, FeatureActivationState.ACTIVE, False),
        (FeatureActivationState.APPROVED, FeatureActivationState.SUSPENDED, False),
        (FeatureActivationState.ACTIVE, FeatureActivationState.ACTIVE, False),
    ],
)
def test_activation_matrix_edges(
    current: FeatureActivationState | None,
    target: FeatureActivationState,
    allowed: bool,
) -> None:
    if current == FeatureActivationState.RETIRED:
        with pytest.raises(AppError):
            validate_activation_transition(current, target)
        return
    if current == target:
        assert validate_activation_transition(current, target) is False
        return
    if allowed:
        assert validate_activation_transition(current, target) is True
    else:
        with pytest.raises(AppError):
            validate_activation_transition(current, target)


def test_openapi_governance_routes_bounded(db_app) -> None:
    paths = db_app.openapi()["paths"]
    governance_paths = [path for path in paths if "/governance/" in path]
    assert governance_paths
    for path in governance_paths:
        for method, _operation in paths[path].items():
            if method == "parameters":
                continue
            assert "delete" not in method.lower()
