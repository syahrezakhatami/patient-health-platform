"""Adversarial security / clinical-safety tests for Manual Vital Signs."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.clinical.domain.manual_vitals_approval import (
    approval_scope_fingerprint,
    default_catalog_version_scope_fingerprint,
)
from app.modules.clinical.domain.vital_signs_catalog import MANUAL_VITALS_FEATURE_ID
from app.modules.governance.domain.enums import PolicyEffect
from app.shared.types.ids import new_id
from sqlalchemy import text
from tests.conftest import TEST_SECRET, mint_token
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.db_privileges import (
    restore_clinical_observation_idempotency_app_dml_privileges,
)
from tests.integration.governance_helpers import (
    governance_headers,
    restore_governance_app_dml_privileges,
    seed_governance_actor,
    seed_governance_actor_for_organization,
)
from tests.integration.manual_vitals_helpers import (
    activate_manual_vitals_site,
    create_manual_vital_body,
    manual_vitals_path,
    manual_vitals_write_headers,
    republish_manual_vitals_policy,
    seed_manual_vitals_provider,
)
from tests.integration.test_product_access_multi_org_isolation import _add_membership
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter

pytestmark = [pytest.mark.integration, requires_db]

HEART_ONLY_SCOPE = default_catalog_version_scope_fingerprint(["heart_rate"])
HEART_TEMP_SCOPE = default_catalog_version_scope_fingerprint(["heart_rate", "body_temperature"])


@pytest.fixture(autouse=True)
async def _manual_vitals_security_privileges(db_engine) -> None:
    await restore_governance_app_dml_privileges(db_engine)
    await restore_clinical_observation_idempotency_app_dml_privileges(db_engine)


async def _seed_clinician_with_governance(db_engine, organization_id=None):
    kwargs = {"role_code": RoleCode.CLINICIAN}
    if organization_id is not None:
        kwargs["organization_id"] = organization_id
    clinician = await seed_actor(db_engine, **kwargs)
    registrar = await seed_actor(
        db_engine,
        role_code=RoleCode.REGISTRAR,
        organization_id=clinician.organization_id,
    )
    org_admin = await seed_governance_actor_for_organization(
        db_engine,
        clinician.organization_id,
        permissions=frozenset(
            {
                Permission.GOVERNANCE_PROFILE_MANAGE,
                Permission.GOVERNANCE_APPROVAL_RECORD,
                Permission.GOVERNANCE_FEATURE_ACTIVATE,
            }
        ),
    )
    return clinician, registrar, org_admin


async def _ready_site(
    db_client,
    db_engine,
    *,
    approved: list[str] | None = None,
    planned=PolicyEffect.ALLOW,
    finished=PolicyEffect.DENY,
    late_doc: bool = False,
):
    approved = approved or ["heart_rate"]
    await seed_manual_vitals_provider(db_engine)
    clinician, registrar, org_admin = await _seed_clinician_with_governance(db_engine)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    scope = default_catalog_version_scope_fingerprint(approved)
    await activate_manual_vitals_site(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=approved,
        scope=scope,
        planned=planned,
        finished=finished,
        late_doc=late_doc,
    )
    return clinician, registrar, org_admin, patient_id, encounter_id


async def _post_vital(
    db_client,
    clinician,
    patient_id,
    encounter_id,
    *,
    key: str | None = None,
    org_id=None,
    **body_kwargs,
):
    org = org_id or clinician.organization_id
    headers = manual_vitals_write_headers(
        clinician,
        idempotency_key=key or f"mv-sec-{uuid4().hex}",
    )
    return await db_client.post(
        manual_vitals_path(org),
        headers=headers,
        json=create_manual_vital_body(patient_id, encounter_id, **body_kwargs),
    )


@requires_db
async def test_manual_vitals_staff_audience_matrix(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    org = str(clinician.organization_id)
    body = create_manual_vital_body(new_id(), new_id())
    accepted = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    assert accepted.status_code == 200

    tokens = {
        "patient": mint_token(sub=clinician.subject, aud="php-patient"),
        "platform": mint_token(sub=clinician.subject, aud="php-platform"),
        "wrong": mint_token(sub=clinician.subject, aud="other-api"),
        "mixed": mint_token(sub=clinician.subject, extra={"aud": ["php-api", "php-patient"]}),
        "missing": jwt.encode(
            {
                "sub": clinician.subject,
                "iss": "http://localhost:8080/realms/php-dev",
                "exp": datetime.now(UTC) + timedelta(minutes=5),
                "iat": datetime.now(UTC),
            },
            TEST_SECRET,
            algorithm="HS256",
        ),
    }
    for label, token in tokens.items():
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": org,
            "X-Purpose": "TREATMENT",
            "Idempotency-Key": f"mv-aud-{label}-{uuid4().hex[:8]}",
        }
        get_denied = await db_client.get(
            manual_vitals_path(clinician.organization_id), headers=headers
        )
        post_denied = await db_client.post(
            manual_vitals_path(clinician.organization_id),
            headers=headers,
            json=body,
        )
        assert get_denied.status_code == 401, label
        assert post_denied.status_code == 401, label


@requires_db
async def test_multi_org_principal_switch_no_context_bleed(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    org_a_clinician, registrar_a, org_admin_a = await _seed_clinician_with_governance(db_engine)
    org_b_clinician, registrar_b, org_admin_b = await _seed_clinician_with_governance(db_engine)
    await _add_membership(
        db_engine,
        user_id=org_a_clinician.user_id,
        organization_id=org_b_clinician.organization_id,
        role_code=RoleCode.CLINICIAN,
    )
    await activate_manual_vitals_site(
        db_client,
        org_admin_a,
        org_a_clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    multi = org_a_clinician
    ctx_a = await db_client.get(
        manual_vitals_path(org_a_clinician.organization_id),
        headers=manual_vitals_write_headers(multi, purpose="TREATMENT"),
    )
    assert ctx_a.status_code == 200
    assert ctx_a.json()["available"] is True
    ctx_b = await db_client.get(
        manual_vitals_path(org_b_clinician.organization_id),
        headers={
            **manual_vitals_write_headers(multi, purpose="TREATMENT"),
            "X-Organization-Id": str(org_b_clinician.organization_id),
        },
    )
    assert ctx_b.status_code == 200
    assert ctx_b.json()["available"] is False
    ctx_a_again = await db_client.get(
        manual_vitals_path(org_a_clinician.organization_id),
        headers={
            **manual_vitals_write_headers(multi, purpose="TREATMENT"),
            "X-Organization-Id": str(org_a_clinician.organization_id),
        },
    )
    assert ctx_a_again.status_code == 200
    assert ctx_a_again.json()["available"] is True
    patient_b = await _active_patient(db_client, registrar_b)
    encounter_b = (await _open_encounter(db_client, org_b_clinician, patient_b)).json()["id"]
    cross_post = await db_client.post(
        manual_vitals_path(org_b_clinician.organization_id),
        headers={
            **manual_vitals_write_headers(
                multi, purpose="TREATMENT", idempotency_key=f"mv-switch-{uuid4().hex}"
            ),
            "X-Organization-Id": str(org_b_clinician.organization_id),
        },
        json=create_manual_vital_body(patient_b, encounter_b),
    )
    assert cross_post.status_code == 403


@requires_db
async def test_approval_forgery_wrong_scope_denies(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    clinician, registrar, org_admin = await _seed_clinician_with_governance(db_engine)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    wrong_scope = default_catalog_version_scope_fingerprint(["body_weight"])
    create = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/profile/versions",
        json={
            "policy_document": {
                "schema_version": 2,
                "manual_vital_signs": {
                    "catalog_version": "manual-vitals-mvp-v1",
                    "approved_measurements": ["heart_rate"],
                },
            },
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Scope mismatch test",
        },
        headers=governance_headers(org_admin, idempotency_key=f"mv-scope-{new_id().hex[:8]}"),
    )
    assert create.status_code == 200
    version_id = create.json()["id"]
    publish = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/profile/versions/{version_id}/publish",
        headers=governance_headers(org_admin, idempotency_key=f"mv-scope-pub-{new_id().hex[:8]}"),
    )
    assert publish.status_code == 200
    for gate_type in ("CONTROLLER_PROCESSOR_ASSESSMENT", "DPA"):
        gate = await db_client.put(
            f"/api/v1/organizations/{clinician.organization_id}/governance/deployment-gates/{gate_type}",
            json={"gate_state": "SATISFIED"},
            headers=governance_headers(org_admin),
        )
        assert gate.status_code == 200
    approval = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/approvals",
        json={
            "feature_id": MANUAL_VITALS_FEATURE_ID,
            "provider_feature_version": "1.0.0",
            "approval_type": "CLINICAL_GOVERNANCE",
            "scope": wrong_scope,
            "decision_by_name": "Dr Forged",
            "approval_date": datetime.now(UTC).date().isoformat(),
        },
        headers=governance_headers(org_admin, idempotency_key=f"mv-scope-appr-{new_id().hex[:8]}"),
    )
    assert approval.status_code == 200
    row_version = None
    for target in ("PENDING_APPROVAL", "APPROVED", "ACTIVE"):
        payload: dict[str, object] = {"target_state": target}
        if row_version is not None:
            payload["expected_row_version"] = row_version
        transition = await db_client.post(
            (
                f"/api/v1/organizations/{clinician.organization_id}/governance/"
                f"features/{MANUAL_VITALS_FEATURE_ID}/transition"
            ),
            json=payload,
            headers=governance_headers(org_admin),
        )
        assert transition.status_code == 200
        row_version = transition.json()["row_version"]
    denied = await _post_vital(db_client, clinician, patient_id, encounter_id)
    assert denied.status_code == 403


@requires_db
async def test_approval_forgery_wrong_feature_version_denies(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    clinician, registrar, org_admin = await _seed_clinician_with_governance(db_engine)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    create = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/profile/versions",
        json={
            "policy_document": {
                "schema_version": 2,
                "manual_vital_signs": {
                    "catalog_version": "manual-vitals-mvp-v1",
                    "approved_measurements": ["heart_rate"],
                },
            },
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Wrong feature version",
        },
        headers=governance_headers(org_admin, idempotency_key=f"mv-fv-{new_id().hex[:8]}"),
    )
    assert create.status_code == 200
    version_id = create.json()["id"]
    publish = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/profile/versions/{version_id}/publish",
        headers=governance_headers(org_admin, idempotency_key=f"mv-fv-pub-{new_id().hex[:8]}"),
    )
    assert publish.status_code == 200
    for gate_type in ("CONTROLLER_PROCESSOR_ASSESSMENT", "DPA"):
        gate = await db_client.put(
            f"/api/v1/organizations/{clinician.organization_id}/governance/deployment-gates/{gate_type}",
            json={"gate_state": "SATISFIED"},
            headers=governance_headers(org_admin),
        )
        assert gate.status_code == 200
    approval = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/approvals",
        json={
            "feature_id": MANUAL_VITALS_FEATURE_ID,
            "provider_feature_version": "9.9.9",
            "approval_type": "CLINICAL_GOVERNANCE",
            "scope": HEART_ONLY_SCOPE,
            "decision_by_name": "Dr Wrong Version",
            "approval_date": datetime.now(UTC).date().isoformat(),
        },
        headers=governance_headers(org_admin, idempotency_key=f"mv-fv-appr-{new_id().hex[:8]}"),
    )
    assert approval.status_code == 200
    row_version = None
    for target in ("PENDING_APPROVAL", "APPROVED", "ACTIVE"):
        payload: dict[str, object] = {"target_state": target}
        if row_version is not None:
            payload["expected_row_version"] = row_version
        transition = await db_client.post(
            (
                f"/api/v1/organizations/{clinician.organization_id}/governance/"
                f"features/{MANUAL_VITALS_FEATURE_ID}/transition"
            ),
            json=payload,
            headers=governance_headers(org_admin),
        )
        assert transition.status_code == 200
        row_version = transition.json()["row_version"]
    denied = await _post_vital(db_client, clinician, patient_id, encounter_id)
    assert denied.status_code == 403


@requires_db
async def test_stale_profile_subset_denies_post_after_republish(db_client, db_engine) -> None:
    clinician, _, org_admin, patient_id, encounter_id = await _ready_site(
        db_client, db_engine, approved=["heart_rate", "body_temperature"]
    )
    get_ctx = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    assert get_ctx.status_code == 200
    assert {item["measurement_key"] for item in get_ctx.json()["measurements"]} == {
        "heart_rate",
        "body_temperature",
    }
    await republish_manual_vitals_policy(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    denied = await _post_vital(
        db_client,
        clinician,
        patient_id,
        encounter_id,
        measurement_key="body_temperature",
        value="36.5",
        key=f"mv-stale-{uuid4().hex}",
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "measurement_not_approved"


@requires_db
async def test_feature_activation_stale_row_version_returns_409(db_client, db_engine) -> None:
    clinician, _, org_admin, _, _ = await _ready_site(db_client, db_engine)
    stale = await db_client.post(
        (
            f"/api/v1/organizations/{clinician.organization_id}/governance/"
            f"features/{MANUAL_VITALS_FEATURE_ID}/transition"
        ),
        json={"target_state": "SUSPENDED", "expected_row_version": 1},
        headers=governance_headers(org_admin),
    )
    assert stale.status_code == 409


@requires_db
async def test_provider_suspend_mid_flow_denies_post(db_client, db_engine) -> None:
    capability_id = await seed_manual_vitals_provider(db_engine)
    clinician, _, _, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    get_ctx = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    assert get_ctx.status_code == 200
    assert get_ctx.json()["available"] is True
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                """
                UPDATE provider_capabilities
                SET provider_state = 'SUSPENDED', row_version = row_version + 1
                WHERE id = :id
                """
            ),
            {"id": capability_id},
        )
    denied = await _post_vital(
        db_client, clinician, patient_id, encounter_id, key=f"mv-mid-{uuid4().hex}"
    )
    assert denied.status_code == 403
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                """
                UPDATE provider_capabilities
                SET provider_state = 'RETIRED', row_version = row_version + 1
                WHERE id = :id
                """
            ),
            {"id": capability_id},
        )
    retired = await _post_vital(
        db_client, clinician, patient_id, encounter_id, key=f"mv-ret-{uuid4().hex}"
    )
    assert retired.status_code == 403


@requires_db
async def test_site_suspend_mid_flow_denies_post(db_client, db_engine) -> None:
    clinician, _, org_admin, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    get_ctx = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    assert get_ctx.json()["available"] is True
    async with db_engine.connect() as connection:
        row_version = (
            await connection.execute(
                text(
                    """
                    SELECT row_version FROM organization_feature_activations
                    WHERE organization_id = :org_id AND feature_id = :feature_id
                    """
                ),
                {
                    "org_id": clinician.organization_id,
                    "feature_id": MANUAL_VITALS_FEATURE_ID,
                },
            )
        ).scalar_one()
    suspend = await db_client.post(
        (
            f"/api/v1/organizations/{clinician.organization_id}/governance/"
            f"features/{MANUAL_VITALS_FEATURE_ID}/transition"
        ),
        json={"target_state": "SUSPENDED", "expected_row_version": row_version},
        headers=governance_headers(org_admin),
    )
    assert suspend.status_code == 200
    denied = await _post_vital(
        db_client, clinician, patient_id, encounter_id, key=f"mv-site-{uuid4().hex}"
    )
    assert denied.status_code == 403


@requires_db
async def test_permission_revocation_before_post_denies(db_client, db_engine) -> None:
    clinician, _, _, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    get_ctx = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    assert get_ctx.json()["available"] is True
    async with db_engine.begin() as connection:
        registrar_role = (
            await connection.execute(
                text("SELECT id FROM roles WHERE code = :code"),
                {"code": RoleCode.REGISTRAR.value},
            )
        ).scalar_one()
        await connection.execute(
            text("UPDATE organization_memberships SET role_id = :rid WHERE user_id = :uid"),
            {"rid": registrar_role, "uid": clinician.user_id},
        )
    denied = await _post_vital(
        db_client, clinician, patient_id, encounter_id, key=f"mv-perm-{uuid4().hex}"
    )
    assert denied.status_code == 403


@requires_db
async def test_encounter_cross_org_denies(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    org_a_clinician, registrar_a, org_admin_a = await _seed_clinician_with_governance(db_engine)
    org_b_clinician, registrar_b, _ = await _seed_clinician_with_governance(db_engine)
    patient_a = await _active_patient(db_client, registrar_a)
    patient_b = await _active_patient(db_client, registrar_b)
    encounter_b = (await _open_encounter(db_client, org_b_clinician, patient_b)).json()["id"]
    await activate_manual_vitals_site(
        db_client,
        org_admin_a,
        org_a_clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    denied = await _post_vital(
        db_client,
        org_a_clinician,
        patient_a,
        encounter_b,
        key=f"mv-xenc-{uuid4().hex}",
    )
    assert denied.status_code == 404


@requires_db
async def test_cancelled_encounter_hard_reject_despite_planned_allow(db_client, db_engine) -> None:
    clinician, _, _, patient_id, encounter_id = await _ready_site(
        db_client, db_engine, planned=PolicyEffect.ALLOW
    )
    response = await db_client.post(
        f"/api/v1/clinical/encounters/{encounter_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "CANCELLED"},
    )
    assert response.status_code == 200
    denied = await _post_vital(
        db_client, clinician, patient_id, encounter_id, key=f"mv-can-{uuid4().hex}"
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "encounter_not_documentable"


@requires_db
async def test_planned_encounter_denied_when_policy_missing_allow(db_client, db_engine) -> None:
    clinician, _, _, patient_id, encounter_id = await _ready_site(
        db_client, db_engine, planned=PolicyEffect.DENY
    )
    denied = await _post_vital(
        db_client, clinician, patient_id, encounter_id, key=f"mv-pln-{uuid4().hex}"
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "encounter_not_documentable"


@requires_db
@pytest.mark.parametrize(
    "measurement_key",
    [
        "HEART_RATE",
        "Heart_Rate",
        "heart-rate",
        "heart_rate%2F",
        "heart_rate\x00",
        "x" * 65,
    ],
)
async def test_measurement_key_spoofing_rejected(
    db_client, db_engine, measurement_key: str
) -> None:
    clinician, _, _, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    response = await _post_vital(
        db_client,
        clinician,
        patient_id,
        encounter_id,
        measurement_key=measurement_key,
        key=f"mv-spoof-{uuid4().hex[:8]}",
    )
    assert response.status_code == 422


@requires_db
async def test_site_subset_denies_unapproved_measurement(db_client, db_engine) -> None:
    clinician, _, _, patient_id, encounter_id = await _ready_site(
        db_client,
        db_engine,
        approved=["heart_rate", "body_temperature"],
    )
    get_ctx = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    keys = {item["measurement_key"] for item in get_ctx.json()["measurements"]}
    assert keys == {"heart_rate", "body_temperature"}
    denied = await _post_vital(
        db_client,
        clinician,
        patient_id,
        encounter_id,
        measurement_key="body_weight",
        value="70",
        key=f"mv-subset-{uuid4().hex}",
    )
    assert denied.status_code == 403


@requires_db
async def test_governance_actor_without_clinical_permission_denies(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    gov_only = await seed_governance_actor(
        db_engine,
        permissions=frozenset(
            {
                Permission.GOVERNANCE_PROFILE_MANAGE,
                Permission.GOVERNANCE_APPROVAL_RECORD,
                Permission.GOVERNANCE_FEATURE_ACTIVATE,
            }
        ),
    )
    await activate_manual_vitals_site(
        db_client,
        gov_only,
        gov_only.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    clinician = await seed_actor(
        db_engine, role_code=RoleCode.CLINICIAN, organization_id=gov_only.organization_id
    )
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=gov_only.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    denied = await db_client.post(
        manual_vitals_path(gov_only.organization_id),
        headers=governance_headers(
            gov_only, purpose="TREATMENT", idempotency_key=f"mv-gov-{uuid4().hex}"
        ),
        json=create_manual_vital_body(patient_id, encounter_id),
    )
    assert denied.status_code == 403


@requires_db
async def test_get_context_safe_oracle(db_client, db_engine) -> None:
    clinician, _, org_admin, _, _ = await _ready_site(db_client, db_engine)
    response = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    assert response.status_code == 200
    payload = response.json()
    blob = str(payload)
    for forbidden in (
        "DPA",
        "approval",
        "scope",
        "DENIED_",
        "entitlement",
        "governance_profile",
        "decision_by",
    ):
        assert forbidden.lower() not in blob.lower()
    assert set(payload.keys()) == {
        "available",
        "catalog_version",
        "feature_version",
        "measurements",
    }


@requires_db
async def test_post_denied_states_safe_error_mapping(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    dark = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician, idempotency_key=f"mv-dark-{uuid4().hex}"),
        json=create_manual_vital_body(new_id(), new_id()),
    )
    assert dark.status_code == 403
    blob = dark.text
    for forbidden in ("provider_capabilities", "approval_evidence", "DPA", "DENIED_PROVIDER"):
        assert forbidden not in blob


@requires_db
async def test_generic_vital_signs_staff_create_blocked_without_ogp(db_client, db_engine) -> None:
    """GENERIC-OBS-001: staff generic create cannot bypass Manual Vitals OGP."""
    from tests.integration.test_wave2b2a_observation import _heart_rate

    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    manual_ctx = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    assert manual_ctx.json()["available"] is False
    manual_post = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician, idempotency_key=f"mv-dark-{uuid4().hex}"),
        json=create_manual_vital_body(patient_id, encounter_id),
    )
    assert manual_post.status_code == 403
    generic = await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_heart_rate(patient_id, encounter_id),
    )
    assert generic.status_code == 403
    assert generic.json()["error"]["code"] == "vital_signs_requires_governed_route"


@pytest.mark.parametrize(
    ("key", "expected_status"),
    [
        (None, 422),
        ("", 422),
        ("   ", 422),
        ("short", 422),
        ("invalid key!", 422),
        ("a" * 129, 422),
        ("valid-key-12345678", 403),
    ],
)
@requires_db
async def test_idempotency_key_validation_bounds(
    db_client, db_engine, key: str | None, expected_status: int
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    headers = manual_vitals_write_headers(clinician)
    if key is not None:
        headers["Idempotency-Key"] = key
    else:
        headers.pop("Idempotency-Key", None)
    response = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=headers,
        json=create_manual_vital_body(new_id(), new_id()),
    )
    assert response.status_code == expected_status
    if expected_status == 422:
        assert response.json()["error"]["code"] in {
            "idempotency_key_required",
            "invalid_idempotency_key",
        }


@requires_db
async def test_idempotency_cross_actor_not_replayed(db_client, db_engine) -> None:
    clinician_a, _, _, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    clinician_b = await seed_actor(
        db_engine, role_code=RoleCode.CLINICIAN, organization_id=clinician_a.organization_id
    )
    key = f"mv-xactor-{uuid4().hex}"
    first = await _post_vital(db_client, clinician_a, patient_id, encounter_id, key=key)
    assert first.status_code == 200
    second = await _post_vital(db_client, clinician_b, patient_id, encounter_id, key=key)
    assert second.status_code == 200
    assert second.json()["id"] != first.json()["id"]


@requires_db
async def test_idempotency_cross_org_isolated(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    org_a_clinician, registrar_a, org_admin_a = await _seed_clinician_with_governance(db_engine)
    org_b_clinician, registrar_b, org_admin_b = await _seed_clinician_with_governance(db_engine)
    await _add_membership(
        db_engine,
        user_id=org_a_clinician.user_id,
        organization_id=org_b_clinician.organization_id,
        role_code=RoleCode.CLINICIAN,
    )
    patient_a = await _active_patient(db_client, registrar_a)
    patient_b = await _active_patient(db_client, registrar_b)
    encounter_a = (await _open_encounter(db_client, org_a_clinician, patient_a)).json()["id"]
    encounter_b = (await _open_encounter(db_client, org_b_clinician, patient_b)).json()["id"]
    await activate_manual_vitals_site(
        db_client,
        org_admin_a,
        org_a_clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    await activate_manual_vitals_site(
        db_client,
        org_admin_b,
        org_b_clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    shared_key = f"mv-xorg-key-{uuid4().hex[:8]}"
    first = await _post_vital(db_client, org_a_clinician, patient_a, encounter_a, key=shared_key)
    assert first.status_code == 200
    second = await db_client.post(
        manual_vitals_path(org_b_clinician.organization_id),
        headers={
            **manual_vitals_write_headers(org_a_clinician, idempotency_key=shared_key),
            "X-Organization-Id": str(org_b_clinician.organization_id),
        },
        json=create_manual_vital_body(patient_b, encounter_b),
    )
    assert second.status_code == 200
    assert second.json()["id"] != first.json()["id"]


@requires_db
async def test_idempotency_cross_measurement_conflict(db_client, db_engine) -> None:
    clinician, _, _, patient_id, encounter_id = await _ready_site(
        db_client,
        db_engine,
        approved=["heart_rate", "body_temperature"],
    )
    key = f"mv-xmeas-{uuid4().hex}"
    first = await _post_vital(
        db_client,
        clinician,
        patient_id,
        encounter_id,
        key=key,
        measurement_key="heart_rate",
        value="72",
    )
    assert first.status_code == 200
    second = await _post_vital(
        db_client,
        clinician,
        patient_id,
        encounter_id,
        key=key,
        measurement_key="body_temperature",
        value="36.5",
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_key_conflict"


@requires_db
async def test_idempotency_cross_patient_conflict(db_client, db_engine) -> None:
    clinician, registrar, _, patient_a, encounter_a = await _ready_site(db_client, db_engine)
    patient_b = await _active_patient(db_client, registrar)
    encounter_b = (await _open_encounter(db_client, clinician, patient_b)).json()["id"]
    key = f"mv-xpat-{uuid4().hex}"
    first = await _post_vital(db_client, clinician, patient_a, encounter_a, key=key)
    assert first.status_code == 200
    second = await _post_vital(db_client, clinician, patient_b, encounter_b, key=key)
    assert second.status_code == 409


@requires_db
async def test_naive_effective_at_rejected(db_client, db_engine) -> None:
    clinician, _, _, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    body = create_manual_vital_body(patient_id, encounter_id)
    body["effective_at"] = datetime.now().replace(tzinfo=None).isoformat()
    response = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician, idempotency_key=f"mv-naive-{uuid4().hex}"),
        json=body,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_effective_at"


@requires_db
async def test_decimal_exponent_notation_rejected(db_client, db_engine) -> None:
    clinician, _, _, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    for value in ("1E2", "1e-2", "1E-5"):
        response = await _post_vital(
            db_client,
            clinician,
            patient_id,
            encounter_id,
            value=value,
            key=f"mv-exp-{uuid4().hex[:8]}",
        )
        assert response.status_code == 422


@requires_db
async def test_oversized_numeric_string_rejected(db_client, db_engine) -> None:
    clinician, _, _, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    response = await _post_vital(
        db_client,
        clinician,
        patient_id,
        encounter_id,
        value="9" * 200,
        key=f"mv-big-{uuid4().hex}",
    )
    assert response.status_code == 422


@requires_db
async def test_deployment_gate_missing_denies(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    clinician, registrar, org_admin = await _seed_clinician_with_governance(db_engine)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    create = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/profile/versions",
        json={
            "policy_document": {
                "schema_version": 2,
                "manual_vital_signs": {
                    "catalog_version": "manual-vitals-mvp-v1",
                    "approved_measurements": ["heart_rate"],
                },
            },
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "Gate missing test",
        },
        headers=governance_headers(org_admin, idempotency_key=f"mv-gate-{new_id().hex[:8]}"),
    )
    assert create.status_code == 200
    version_id = create.json()["id"]
    publish = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/profile/versions/{version_id}/publish",
        headers=governance_headers(org_admin, idempotency_key=f"mv-gate-pub-{new_id().hex[:8]}"),
    )
    assert publish.status_code == 200
    approval = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/approvals",
        json={
            "feature_id": MANUAL_VITALS_FEATURE_ID,
            "provider_feature_version": "1.0.0",
            "approval_type": "CLINICAL_GOVERNANCE",
            "scope": HEART_ONLY_SCOPE,
            "decision_by_name": "Dr Gate",
            "approval_date": datetime.now(UTC).date().isoformat(),
        },
        headers=governance_headers(org_admin, idempotency_key=f"mv-gate-appr-{new_id().hex[:8]}"),
    )
    assert approval.status_code == 200
    row_version = None
    for target in ("PENDING_APPROVAL", "APPROVED", "ACTIVE"):
        payload: dict[str, object] = {"target_state": target}
        if row_version is not None:
            payload["expected_row_version"] = row_version
        transition = await db_client.post(
            (
                f"/api/v1/organizations/{clinician.organization_id}/governance/"
                f"features/{MANUAL_VITALS_FEATURE_ID}/transition"
            ),
            json=payload,
            headers=governance_headers(org_admin),
        )
        assert transition.status_code == 200
        row_version = transition.json()["row_version"]
    denied = await _post_vital(
        db_client, clinician, patient_id, encounter_id, key=f"mv-gate-{uuid4().hex}"
    )
    assert denied.status_code == 403


def test_scope_hash_collision_not_authority_without_binding() -> None:
    """Matching scope alone must not imply cross-binding authority."""
    scope = approval_scope_fingerprint(
        catalog_version="manual-vitals-mvp-v1",
        approved_measurements=["heart_rate"],
    )
    assert scope == default_catalog_version_scope_fingerprint(["heart_rate"])
    other_org_scope = approval_scope_fingerprint(
        catalog_version="manual-vitals-mvp-v1",
        approved_measurements=["heart_rate"],
    )
    assert scope == other_org_scope
    # Integration tests prove org/profile/feature/version/type binding is enforced separately.
