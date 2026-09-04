from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from app.modules.clinical.domain.vital_signs_catalog import (
    MANUAL_VITALS_CATALOG_VERSION,
    MANUAL_VITALS_FEATURE_ID,
)
from app.modules.governance.domain.enums import (
    DeploymentGateType,
    PolicyEffect,
)
from app.modules.governance.domain.policy_schema import (
    EncounterStatusPolicy,
    GovernancePolicyDocumentV2,
    LateDocumentationPolicy,
    ManualVitalSignsPolicy,
)
from app.shared.types.ids import new_id
from tests.integration.conftest import requires_db
from tests.integration.governance_helpers import (
    governance_headers,
    insert_test_provider_capability,
)

pytestmark = [pytest.mark.integration, requires_db]


def _org_code(prefix: str) -> str:
    return f"{prefix}{new_id().hex[:6]}".upper()


def manual_vitals_policy_v2(
    approved_measurements: list[str],
    *,
    planned: PolicyEffect = PolicyEffect.ALLOW,
    finished: PolicyEffect = PolicyEffect.DENY,
    late_doc: bool = False,
) -> dict[str, object]:
    return GovernancePolicyDocumentV2(
        manual_vital_signs=ManualVitalSignsPolicy(
            catalog_version=MANUAL_VITALS_CATALOG_VERSION,
            approved_measurements=approved_measurements,
        ),
        encounter_status_policy=EncounterStatusPolicy(planned=planned, finished=finished),
        late_documentation_policy=LateDocumentationPolicy(
            finished_encounter_write_allowed=late_doc,
        ),
    ).model_dump(mode="json")


def manual_vitals_write_headers(
    actor,
    *,
    purpose: str = "TREATMENT",
    idempotency_key: str | None = None,
    facility_id: object | None = None,
) -> dict[str, str]:
    headers = actor.headers(purpose=purpose)
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    if facility_id is not None:
        headers["X-Facility-Id"] = str(facility_id)
    return headers


def create_manual_vital_body(
    patient_id: object,
    encounter_id: object,
    *,
    measurement_key: str = "heart_rate",
    value: str | int = "72",
    effective_at: str | None = None,
) -> dict[str, object]:
    return {
        "expected_patient_identity_id": str(patient_id),
        "encounter_id": str(encounter_id),
        "measurement_key": measurement_key,
        "value": value,
        "effective_at": effective_at or datetime.now(UTC).isoformat(),
    }


def manual_vitals_path(organization_id: object) -> str:
    return f"/api/v1/organizations/{organization_id}/clinical/manual-vitals/measurements"


async def seed_manual_vitals_provider(db_engine) -> UUID:
    from sqlalchemy import text

    async with db_engine.connect() as connection:
        existing = (
            await connection.execute(
                text(
                    """
                    SELECT id FROM provider_capabilities
                    WHERE feature_id = :feature_id
                    """
                ),
                {"feature_id": MANUAL_VITALS_FEATURE_ID},
            )
        ).first()
    if existing is not None:
        async with db_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE provider_capabilities
                    SET provider_state = 'AVAILABLE'
                    WHERE id = :capability_id
                    """
                ),
                {"capability_id": existing[0]},
            )
        return existing[0]
    return await insert_test_provider_capability(
        db_engine,
        feature_id=MANUAL_VITALS_FEATURE_ID,
        feature_version="1.0.0",
        governance_required=True,
        required_gates=frozenset(
            {
                DeploymentGateType.CONTROLLER_PROCESSOR_ASSESSMENT,
                DeploymentGateType.DPA,
            }
        ),
    )


async def activate_manual_vitals_site(
    db_client,
    org_admin,
    organization_id,
    *,
    approved_measurements: list[str],
    scope: str,
    planned: PolicyEffect = PolicyEffect.ALLOW,
    finished: PolicyEffect = PolicyEffect.DENY,
    late_doc: bool = False,
) -> None:
    from app.modules.clinical.domain.manual_vitals_approval import approval_scope_fingerprint

    expected_scope = approval_scope_fingerprint(
        catalog_version=MANUAL_VITALS_CATALOG_VERSION,
        approved_measurements=approved_measurements,
    )
    assert expected_scope == scope
    create = await db_client.post(
        f"/api/v1/organizations/{organization_id}/governance/profile/versions",
        json={
            "policy_document": manual_vitals_policy_v2(
                approved_measurements,
                planned=planned,
                finished=finished,
                late_doc=late_doc,
            ),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Manual vitals test profile",
        },
        headers=governance_headers(
            org_admin,
            idempotency_key=f"mv-profile-{new_id().hex[:8]}",
        ),
    )
    assert create.status_code == 200, create.text
    version_id = create.json()["id"]
    publish = await db_client.post(
        f"/api/v1/organizations/{organization_id}/governance/profile/versions/{version_id}/publish",
        headers=governance_headers(
            org_admin,
            idempotency_key=f"mv-publish-{new_id().hex[:8]}",
        ),
    )
    assert publish.status_code == 200, publish.text
    for gate_type in ("CONTROLLER_PROCESSOR_ASSESSMENT", "DPA"):
        gate = await db_client.put(
            f"/api/v1/organizations/{organization_id}/governance/deployment-gates/{gate_type}",
            json={"gate_state": "SATISFIED"},
            headers=governance_headers(org_admin),
        )
        assert gate.status_code == 200, gate.text
    approval = await db_client.post(
        f"/api/v1/organizations/{organization_id}/governance/approvals",
        json={
            "feature_id": MANUAL_VITALS_FEATURE_ID,
            "provider_feature_version": "1.0.0",
            "approval_type": "CLINICAL_GOVERNANCE",
            "scope": scope,
            "decision_by_name": "Dr Example",
            "approval_date": date.today().isoformat(),
        },
        headers=governance_headers(
            org_admin,
            idempotency_key=f"mv-approval-{new_id().hex[:8]}",
        ),
    )
    assert approval.status_code == 200, approval.text
    row_version: int | None = None
    for target in ("PENDING_APPROVAL", "APPROVED", "ACTIVE"):
        payload: dict[str, object] = {"target_state": target}
        if row_version is not None:
            payload["expected_row_version"] = row_version
        transition = await db_client.post(
            (
                f"/api/v1/organizations/{organization_id}/governance/"
                f"features/{MANUAL_VITALS_FEATURE_ID}/transition"
            ),
            json=payload,
            headers=governance_headers(org_admin),
        )
        assert transition.status_code == 200, transition.text
        row_version = transition.json()["row_version"]


async def republish_manual_vitals_policy(
    db_client,
    org_admin,
    organization_id,
    *,
    approved_measurements: list[str],
    scope: str,
    planned: PolicyEffect = PolicyEffect.ALLOW,
    finished: PolicyEffect = PolicyEffect.DENY,
    late_doc: bool = False,
) -> None:
    """Publish a new active profile + approval without feature activation transitions."""
    from app.modules.clinical.domain.manual_vitals_approval import approval_scope_fingerprint

    expected_scope = approval_scope_fingerprint(
        catalog_version=MANUAL_VITALS_CATALOG_VERSION,
        approved_measurements=approved_measurements,
    )
    assert expected_scope == scope
    create = await db_client.post(
        f"/api/v1/organizations/{organization_id}/governance/profile/versions",
        json={
            "policy_document": manual_vitals_policy_v2(
                approved_measurements,
                planned=planned,
                finished=finished,
                late_doc=late_doc,
            ),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Manual vitals republish",
        },
        headers=governance_headers(
            org_admin,
            idempotency_key=f"mv-repub-{new_id().hex[:8]}",
        ),
    )
    assert create.status_code == 200, create.text
    version_id = create.json()["id"]
    publish = await db_client.post(
        f"/api/v1/organizations/{organization_id}/governance/profile/versions/{version_id}/publish",
        headers=governance_headers(
            org_admin,
            idempotency_key=f"mv-repub-pub-{new_id().hex[:8]}",
        ),
    )
    assert publish.status_code == 200, publish.text
    approval = await db_client.post(
        f"/api/v1/organizations/{organization_id}/governance/approvals",
        json={
            "feature_id": MANUAL_VITALS_FEATURE_ID,
            "provider_feature_version": "1.0.0",
            "approval_type": "CLINICAL_GOVERNANCE",
            "scope": scope,
            "decision_by_name": "Dr Example",
            "approval_date": date.today().isoformat(),
        },
        headers=governance_headers(
            org_admin,
            idempotency_key=f"mv-repub-appr-{new_id().hex[:8]}",
        ),
    )
    assert approval.status_code == 200, approval.text
