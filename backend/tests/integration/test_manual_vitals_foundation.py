import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.clinical.domain.manual_vitals_approval import (
    default_catalog_version_scope_fingerprint,
)
from app.modules.governance.domain.policy_schema import GovernancePolicyDocumentV1
from app.shared.types.ids import new_id
from sqlalchemy import text
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.db_privileges import (
    restore_clinical_observation_idempotency_app_dml_privileges,
)
from tests.integration.governance_helpers import (
    governance_headers,
    restore_governance_app_dml_privileges,
    seed_governance_actor_for_organization,
)
from tests.integration.manual_vitals_helpers import (
    activate_manual_vitals_site,
    create_manual_vital_body,
    manual_vitals_path,
    manual_vitals_write_headers,
    seed_manual_vitals_provider,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter

pytestmark = [pytest.mark.integration, requires_db]

HEART_ONLY_SCOPE = default_catalog_version_scope_fingerprint(["heart_rate"])


@pytest.fixture(autouse=True)
async def _manual_vitals_privileges(db_engine) -> None:
    await restore_governance_app_dml_privileges(db_engine)
    await restore_clinical_observation_idempotency_app_dml_privileges(db_engine)


async def _seed_clinician_with_governance(db_engine):
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
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


async def _patient_and_encounter(db_client, db_engine):
    clinician, registrar, org_admin = await _seed_clinician_with_governance(db_engine)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    return clinician, org_admin, patient_id, encounter_id


@pytest.mark.asyncio
async def test_production_dark_unregistered_provider(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    get_resp = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["available"] is False
    assert get_resp.json()["measurements"] == []
    post_resp = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician, idempotency_key=f"mv-dark-{uuid4().hex}"),
        json=create_manual_vital_body(new_id(), new_id()),
    )
    assert post_resp.status_code == 403


@pytest.mark.asyncio
async def test_success_path_creates_final_vital_observation(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    ctx = await _patient_and_encounter(db_client, db_engine)
    clinician, org_admin, patient_id, encounter_id = ctx
    await activate_manual_vitals_site(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    response = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(
            clinician,
            idempotency_key=f"mv-success-{uuid4().hex}",
        ),
        json=create_manual_vital_body(patient_id, encounter_id, value="72"),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["category"] == "VITAL_SIGNS"
    assert payload["status"] == "FINAL"
    assert payload["value_type"] == "NUMERIC"
    assert payload["code"]["code"] == "8867-4"
    assert payload["unit"] == "/min"


@pytest.mark.asyncio
async def test_site_subset_denies_unapproved_measurement(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    ctx = await _patient_and_encounter(db_client, db_engine)
    clinician, org_admin, patient_id, encounter_id = ctx
    await activate_manual_vitals_site(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    response = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(
            clinician,
            idempotency_key=f"mv-subset-{uuid4().hex}",
        ),
        json=create_manual_vital_body(
            patient_id,
            encounter_id,
            measurement_key="body_weight",
            value="70",
        ),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_write_context_returns_approved_subset(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    clinician, org_admin, _, _ = await _patient_and_encounter(db_client, db_engine)
    await activate_manual_vitals_site(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=["heart_rate", "body_temperature"],
        scope=default_catalog_version_scope_fingerprint(["heart_rate", "body_temperature"]),
    )
    response = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    keys = {item["measurement_key"] for item in payload["measurements"]}
    assert keys == {"heart_rate", "body_temperature"}


@pytest.mark.asyncio
async def test_idempotency_same_key_same_semantic_value(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    ctx = await _patient_and_encounter(db_client, db_engine)
    clinician, org_admin, patient_id, encounter_id = ctx
    await activate_manual_vitals_site(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    key = f"mv-idem-{uuid4().hex}"
    effective_at = datetime.now(UTC).isoformat()
    first = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician, idempotency_key=key),
        json=create_manual_vital_body(
            patient_id, encounter_id, value="1.0", effective_at=effective_at
        ),
    )
    second = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician, idempotency_key=key),
        json=create_manual_vital_body(
            patient_id, encounter_id, value="1.00", effective_at=effective_at
        ),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_idempotency_same_key_different_value_conflicts(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    ctx = await _patient_and_encounter(db_client, db_engine)
    clinician, org_admin, patient_id, encounter_id = ctx
    await activate_manual_vitals_site(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    key = f"mv-conflict-{uuid4().hex}"
    first = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician, idempotency_key=key),
        json=create_manual_vital_body(patient_id, encounter_id, value="72"),
    )
    second = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician, idempotency_key=key),
        json=create_manual_vital_body(patient_id, encounter_id, value="73"),
    )
    assert first.status_code == 200
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_provider_suspended_denies(db_client, db_engine) -> None:
    capability_id = await seed_manual_vitals_provider(db_engine)
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
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    response = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(
            clinician,
            idempotency_key=f"mv-susp-{uuid4().hex}",
        ),
        json=create_manual_vital_body(new_id(), new_id()),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_v1_profile_denies_manual_vitals(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    clinician, _, org_admin = await _seed_clinician_with_governance(db_engine)
    create = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/profile/versions",
        json={
            "policy_document": GovernancePolicyDocumentV1().model_dump(mode="json"),
            "effective_at": datetime.now(UTC).isoformat(),
            "reason": "V1 only",
        },
        headers=governance_headers(
            org_admin,
            idempotency_key=f"mv-v1-{new_id().hex[:8]}",
        ),
    )
    assert create.status_code == 200
    version_id = create.json()["id"]
    publish = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/profile/versions/{version_id}/publish",
        headers=governance_headers(
            org_admin,
            idempotency_key=f"mv-v1-pub-{new_id().hex[:8]}",
        ),
    )
    assert publish.status_code == 200
    response = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    assert response.status_code == 200
    assert response.json()["available"] is False


@pytest.mark.asyncio
async def test_concurrent_same_key_one_observation(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    ctx = await _patient_and_encounter(db_client, db_engine)
    clinician, org_admin, patient_id, encounter_id = ctx
    await activate_manual_vitals_site(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    key = f"mv-race-{uuid4().hex}"
    body = create_manual_vital_body(patient_id, encounter_id, value="72")
    headers = manual_vitals_write_headers(clinician, idempotency_key=key)

    async def post_once():
        return await db_client.post(
            manual_vitals_path(clinician.organization_id),
            headers=headers,
            json=body,
        )

    results = await asyncio.gather(post_once(), post_once())
    statuses = {item.status_code for item in results}
    assert statuses == {200}
    ids = {item.json()["id"] for item in results}
    assert len(ids) == 1
    async with db_engine.connect() as connection:
        obs_count = (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*) FROM observations
                    WHERE encounter_id = :encounter_id AND code = '8867-4'
                    """
                ),
                {"encounter_id": encounter_id},
            )
        ).scalar_one()
        idem_count = (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*) FROM clinical_observation_write_idempotency
                    WHERE idempotency_key = :key
                    """
                ),
                {"key": key},
            )
        ).scalar_one()
    assert obs_count == 1
    assert idem_count == 1
