import asyncio
from datetime import UTC, date, datetime, timedelta

import pytest
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.governance.domain.enums import (
    GovernanceDenialReason,
)
from app.modules.governance.domain.policy_schema import GovernancePolicyDocumentV1
from app.shared.types.ids import new_id
from sqlalchemy import text
from tests.conftest import mint_token
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.governance_helpers import (
    governance_headers,
    insert_test_provider_capability,
    platform_headers,
    seed_governance_actor,
)

pytestmark = [pytest.mark.integration, requires_db]


@pytest.fixture(autouse=True)
async def _governance_privileges(db_engine) -> None:
    from tests.integration.governance_helpers import restore_governance_app_dml_privileges

    await restore_governance_app_dml_privileges(db_engine)


def _org_code(prefix: str) -> str:
    return f"{prefix}{new_id().hex[:6]}".upper()


async def _org_admin(db_engine, prefix: str):
    return await seed_actor(
        db_engine,
        role_code=RoleCode.ORG_ADMIN,
        org_code=_org_code(prefix),
    )


async def _clinician(db_engine, prefix: str):
    return await seed_actor(
        db_engine,
        role_code=RoleCode.CLINICIAN,
        org_code=_org_code(prefix),
    )


def _policy() -> dict[str, object]:
    return GovernancePolicyDocumentV1().model_dump(mode="json")


@pytest.mark.asyncio
async def test_migration_empty_provider_registry(db_engine) -> None:
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
async def test_effective_context_empty_registry(db_client, db_engine) -> None:
    clinician = await _clinician(db_engine, "GOV")
    response = await db_client.get(
        f"/api/v1/organizations/{clinician.organization_id}/governance/effective-context",
        headers=governance_headers(clinician, purpose="TREATMENT"),
    )
    assert response.status_code == 200
    payload = response.json()
    feature_ids = {item["feature_id"] for item in payload["governed_features"]}
    assert "clinical_note_write" not in feature_ids
    assert "manual_vital_signs_write" not in feature_ids


@pytest.mark.asyncio
async def test_clinician_effective_context_without_profile_read(db_client, db_engine) -> None:
    clinician = await _clinician(db_engine, "GOV10")
    effective = await db_client.get(
        f"/api/v1/organizations/{clinician.organization_id}/governance/effective-context",
        headers=governance_headers(clinician, purpose="TREATMENT"),
    )
    assert effective.status_code == 200
    profile = await db_client.get(
        f"/api/v1/organizations/{clinician.organization_id}/governance/profile",
        headers=governance_headers(clinician, purpose="TREATMENT"),
    )
    assert profile.status_code == 403


@pytest.mark.asyncio
async def test_cross_org_effective_context_concealed(db_client, db_engine) -> None:
    org_a = await _clinician(db_engine, "GOVAE")
    org_b = await _clinician(db_engine, "GOVBE")
    response = await db_client.get(
        f"/api/v1/organizations/{org_b.organization_id}/governance/effective-context",
        headers=governance_headers(org_a, purpose="TREATMENT"),
    )
    assert response.status_code in {403, 404}


@pytest.mark.asyncio
async def test_cross_org_governance_concealed(db_client, db_engine) -> None:
    org_a = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN, org_code=_org_code("GOVA"))
    org_b = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN, org_code=_org_code("GOVB"))
    response = await db_client.get(
        f"/api/v1/organizations/{org_b.organization_id}/governance/profile",
        headers=governance_headers(org_a),
    )
    assert response.status_code in {403, 404}


@pytest.mark.asyncio
async def test_profile_version_idempotency(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "GOV2")
    body = {
        "policy_document": _policy(),
        "effective_at": datetime.now(UTC).isoformat(),
        "reason": "Initial foundation",
    }
    headers = governance_headers(org_admin, idempotency_key="gov-profile-create-001")
    first = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/profile/versions",
        json=body,
        headers=headers,
    )
    second = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/profile/versions",
        json=body,
        headers=headers,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_profile_version_idempotency_conflict(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "GOV3")
    headers = governance_headers(org_admin, idempotency_key="gov-profile-create-conflict")
    first = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/profile/versions",
        json={
            "policy_document": _policy(),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "One",
        },
        headers=headers,
    )
    second = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/profile/versions",
        json={
            "policy_document": _policy(),
            "effective_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "reason": "Two",
        },
        headers=headers,
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_key_conflict"


@pytest.mark.asyncio
async def test_publish_profile_version(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "GOV4")
    create = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/profile/versions",
        json={
            "policy_document": _policy(),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Publish me",
        },
        headers=governance_headers(org_admin, idempotency_key="gov-profile-create-publish"),
    )
    version_id = create.json()["id"]
    publish = await db_client.post(
        (
            f"/api/v1/organizations/{org_admin.organization_id}/governance/"
            f"profile/versions/{version_id}/publish"
        ),
        headers=governance_headers(org_admin, idempotency_key="gov-profile-publish-001"),
    )
    assert publish.status_code == 200
    assert publish.json()["status"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_provider_capability_platform_list_empty(db_client, db_engine, db_settings) -> None:
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    token = mint_token(sub=platform.subject, aud=db_settings.auth_platform_audience)
    response = await db_client.get(
        "/api/v1/platform/governance/capabilities",
        headers=platform_headers(token),
    )
    assert response.status_code == 200
    feature_ids = {item["feature_id"] for item in response.json()["capabilities"]}
    assert "clinical_note_write" not in feature_ids


@pytest.mark.asyncio
async def test_platform_api_rejects_staff_audience(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "GOV5")
    response = await db_client.get(
        "/api/v1/platform/governance/capabilities",
        headers=governance_headers(org_admin),
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_provider_suspend_and_noop(db_client, db_engine, db_settings) -> None:
    feature_id = f"test_provider_only_{new_id().hex[:8]}"
    await insert_test_provider_capability(
        db_engine,
        feature_id=feature_id,
        governance_required=False,
    )
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    token = mint_token(sub=platform.subject, aud=db_settings.auth_platform_audience)
    suspend = await db_client.post(
        f"/api/v1/platform/governance/capabilities/{feature_id}/transition",
        json={"target_state": "SUSPENDED", "expected_row_version": 1},
        headers=platform_headers(token),
    )
    assert suspend.status_code == 200
    assert suspend.json()["provider_state"] == "SUSPENDED"
    repeat = await db_client.post(
        f"/api/v1/platform/governance/capabilities/{feature_id}/transition",
        json={"target_state": "SUSPENDED", "expected_row_version": 2},
        headers=platform_headers(token),
    )
    assert repeat.status_code == 200
    assert repeat.json()["provider_state"] == "SUSPENDED"
    assert repeat.json()["row_version"] == 2


@pytest.mark.asyncio
async def test_resolver_synthetic_governed_feature(db_client, db_engine) -> None:
    from app.db.session import create_session_factory
    from app.modules.audit.infrastructure.sqlalchemy_sink import SqlAlchemyAuditSink
    from app.modules.authorization.application.product_access_pdp import ProductAccessPDP
    from app.modules.governance.application.services import GovernanceService

    feature_id = f"test_governed_{new_id().hex[:8]}"
    capability_id = await insert_test_provider_capability(
        db_engine,
        feature_id=feature_id,
        governance_required=True,
    )
    org_admin = await _org_admin(db_engine, "GOV6")
    session_factory = create_session_factory(db_engine)
    pdp = ProductAccessPDP()
    async with session_factory() as session:
        service = GovernanceService(
            session,
            pdp,
            SqlAlchemyAuditSink(session),
        )
        missing = await service.resolve_feature(org_admin.organization_id, feature_id)
        assert missing.denial_reason == GovernanceDenialReason.DENIED_SITE_ACTIVATION
        await session.execute(
            text(
                """
                UPDATE provider_capabilities
                SET provider_state = 'SUSPENDED', row_version = 2
                WHERE id = :id
                """
            ),
            {"id": capability_id},
        )
        await session.commit()
    async with session_factory() as session:
        service = GovernanceService(
            session,
            pdp,
            SqlAlchemyAuditSink(session),
        )
        suspended = await service.resolve_feature(org_admin.organization_id, feature_id)
        assert suspended.denial_reason == GovernanceDenialReason.DENIED_PROVIDER


@pytest.mark.asyncio
async def test_permission_separation(db_client, db_engine) -> None:
    profile_manager = await seed_governance_actor(
        db_engine,
        permissions=frozenset({Permission.GOVERNANCE_PROFILE_MANAGE}),
        org_code=_org_code("GOV7A"),
    )
    approval_recorder = await seed_governance_actor(
        db_engine,
        permissions=frozenset({Permission.GOVERNANCE_APPROVAL_RECORD}),
        org_code=_org_code("GOV7B"),
    )
    feature_activator = await seed_governance_actor(
        db_engine,
        permissions=frozenset({Permission.GOVERNANCE_FEATURE_ACTIVATE}),
        org_code=_org_code("GOV7C"),
    )
    approval_body = {
        "feature_id": "test_governed_feature",
        "provider_feature_version": "1.0.0",
        "approval_type": "CLINICAL",
        "scope": "SITE",
        "decision_by_name": "Dr Example",
        "approval_date": date.today().isoformat(),
    }
    denied_by_manager = await db_client.post(
        f"/api/v1/organizations/{profile_manager.organization_id}/governance/approvals",
        json=approval_body,
        headers=governance_headers(profile_manager, idempotency_key="gov-approval-deny-manager"),
    )
    assert denied_by_manager.status_code == 403
    denied_activate_by_manager = await db_client.post(
        (
            f"/api/v1/organizations/{profile_manager.organization_id}/governance/"
            "features/test_governed_feature/transition"
        ),
        json={"target_state": "PENDING_APPROVAL"},
        headers=governance_headers(profile_manager),
    )
    assert denied_activate_by_manager.status_code == 403
    denied_profile_by_approver = await db_client.get(
        f"/api/v1/organizations/{approval_recorder.organization_id}/governance/profile",
        headers=governance_headers(approval_recorder),
    )
    assert denied_profile_by_approver.status_code == 403
    denied_activate_by_approver = await db_client.post(
        (
            f"/api/v1/organizations/{approval_recorder.organization_id}/governance/"
            "features/test_governed_feature/transition"
        ),
        json={"target_state": "PENDING_APPROVAL"},
        headers=governance_headers(approval_recorder),
    )
    assert denied_activate_by_approver.status_code == 403
    denied_approval_by_activator = await db_client.post(
        f"/api/v1/organizations/{feature_activator.organization_id}/governance/approvals",
        json=approval_body,
        headers=governance_headers(
            feature_activator, idempotency_key="gov-approval-deny-activator"
        ),
    )
    assert denied_approval_by_activator.status_code == 403
    denied_profile_edit_by_activator = await db_client.post(
        f"/api/v1/organizations/{feature_activator.organization_id}/governance/profile/versions",
        json={
            "policy_document": _policy(),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Denied",
        },
        headers=governance_headers(feature_activator, idempotency_key="gov-profile-deny-activator"),
    )
    assert denied_profile_edit_by_activator.status_code == 403


@pytest.mark.asyncio
async def test_platform_provider_manager_clinical_boundary(
    db_client, db_engine, db_settings
) -> None:
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    token = mint_token(sub=platform.subject, aud=db_settings.auth_platform_audience)
    capabilities = await db_client.get(
        "/api/v1/platform/governance/capabilities",
        headers=platform_headers(token),
    )
    assert capabilities.status_code == 200
    mpi = await db_client.get(
        f"/api/v1/mpi/identities/{clinician.organization_id}",
        headers=platform_headers(token),
    )
    assert mpi.status_code in {401, 403, 404}
    note = await db_client.post(
        "/api/v1/clinical/notes",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
        json={
            "expected_patient_identity_id": str(new_id()),
            "encounter_id": str(new_id()),
            "note_type": "PROGRESS",
            "body_text": "blocked",
        },
    )
    assert note.status_code in {401, 403, 404, 422}


@pytest.mark.asyncio
async def test_org_admin_lacks_default_approval_and_activate(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "GOV7D")
    approval = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/approvals",
        json={
            "feature_id": "test_governed_feature",
            "provider_feature_version": "1.0.0",
            "approval_type": "CLINICAL",
            "scope": "SITE",
            "decision_by_name": "Dr Example",
            "approval_date": date.today().isoformat(),
        },
        headers=governance_headers(org_admin, idempotency_key="gov-approval-deny-org-admin"),
    )
    assert approval.status_code == 403
    activate = await db_client.post(
        (
            f"/api/v1/organizations/{org_admin.organization_id}/governance/"
            "features/test_governed_feature/transition"
        ),
        json={"target_state": "PENDING_APPROVAL"},
        headers=governance_headers(org_admin),
    )
    assert activate.status_code == 403


@pytest.mark.asyncio
async def test_published_profile_version_immutable(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "GOV8")
    create = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/governance/profile/versions",
        json={
            "policy_document": _policy(),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Immutable test",
        },
        headers=governance_headers(
            org_admin,
            idempotency_key=f"gov-immutable-create-{new_id().hex[:8]}",
        ),
    )
    assert create.status_code == 200
    version_id = create.json()["id"]
    publish = await db_client.post(
        (
            f"/api/v1/organizations/{org_admin.organization_id}/governance/"
            f"profile/versions/{version_id}/publish"
        ),
        headers=governance_headers(
            org_admin,
            idempotency_key=f"gov-immutable-publish-{new_id().hex[:8]}",
        ),
    )
    assert publish.status_code == 200
    with pytest.raises(Exception, match="immutable"):
        async with db_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE organization_governance_profile_versions
                    SET reason = 'changed'
                    WHERE id = :version_id
                    """
                ),
                {"version_id": version_id},
            )


@pytest.mark.asyncio
async def test_concurrent_profile_version_idempotency(db_client, db_engine) -> None:
    org_admin = await _org_admin(db_engine, "GOV9")
    body = {
        "policy_document": _policy(),
        "effective_at": datetime.now(UTC).isoformat(),
        "reason": "Concurrent",
    }
    headers = governance_headers(org_admin, idempotency_key=f"gov-concurrent-{new_id().hex[:8]}")

    async def _create() -> int:
        response = await db_client.post(
            f"/api/v1/organizations/{org_admin.organization_id}/governance/profile/versions",
            json=body,
            headers=headers,
        )
        return response.status_code

    statuses = await asyncio.gather(_create(), _create())
    assert all(status == 200 for status in statuses)
