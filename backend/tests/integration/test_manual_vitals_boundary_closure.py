"""Final security closure: generic Observation boundary + governance TOCTOU."""

import asyncio
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.clinical.domain.manual_vitals_approval import (
    default_catalog_version_scope_fingerprint,
)
from app.modules.clinical.domain.vital_signs_catalog import MANUAL_VITALS_FEATURE_ID
from sqlalchemy import text
from tests.conftest import mint_token
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.db_privileges import (
    restore_clinical_observation_idempotency_app_dml_privileges,
)
from tests.integration.governance_helpers import (
    governance_headers,
    platform_headers,
    restore_governance_app_dml_privileges,
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
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave2b2a_observation import _generic_exam_observation, _heart_rate

pytestmark = [pytest.mark.integration, requires_db]

HEART_ONLY_SCOPE = default_catalog_version_scope_fingerprint(["heart_rate"])


@pytest.fixture(autouse=True)
async def _boundary_closure_privileges(db_engine) -> None:
    await restore_governance_app_dml_privileges(db_engine)
    await restore_clinical_observation_idempotency_app_dml_privileges(db_engine)


async def _ready_site(db_client, db_engine):
    await seed_manual_vitals_provider(db_engine)
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
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
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    await activate_manual_vitals_site(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    return clinician, org_admin, patient_id, encounter_id


async def _post_vital(db_client, clinician, patient_id, encounter_id, *, key: str | None = None):
    return await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(
            clinician,
            idempotency_key=key or f"mv-bc-{uuid4().hex}",
        ),
        json=create_manual_vital_body(patient_id, encounter_id),
    )


@requires_db
async def test_production_dark_both_routes_fail_closed(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    manual = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician, idempotency_key=f"mv-pd-{uuid4().hex}"),
        json=create_manual_vital_body(patient_id, encounter_id),
    )
    assert manual.status_code == 403
    generic = await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_heart_rate(patient_id, encounter_id),
    )
    assert generic.status_code == 403
    assert generic.json()["error"]["code"] == "vital_signs_requires_governed_route"


@requires_db
async def test_generic_exam_observation_still_allowed(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    created = await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_generic_exam_observation(patient_id, encounter_id),
    )
    assert created.status_code in {200, 201}
    assert created.json()["category"] == "EXAM"


@requires_db
async def test_concurrent_provider_suspend_and_manual_vital_post(
    db_client, db_engine, db_settings
) -> None:
    clinician, _, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    token = mint_token(sub=platform.subject, aud=db_settings.auth_platform_audience)
    async with db_engine.connect() as connection:
        row_version = (
            await connection.execute(
                text(
                    """
                    SELECT row_version FROM provider_capabilities
                    WHERE feature_id = :feature_id
                    """
                ),
                {"feature_id": MANUAL_VITALS_FEATURE_ID},
            )
        ).scalar_one()
        before_count = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM observations
                    WHERE patient_identity_id = :pid AND code = '8867-4'
                    """
                ),
                {"pid": patient_id},
            )
        ).scalar_one()

    async def suspend_provider():
        return await db_client.post(
            f"/api/v1/platform/governance/capabilities/{MANUAL_VITALS_FEATURE_ID}/transition",
            json={"target_state": "SUSPENDED", "expected_row_version": row_version},
            headers=platform_headers(token),
        )

    post, suspend = await asyncio.gather(
        _post_vital(db_client, clinician, patient_id, encounter_id, key=f"mv-race-{uuid4().hex}"),
        suspend_provider(),
    )
    assert suspend.status_code == 200
    async with db_engine.connect() as connection:
        after_count = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM observations
                    WHERE patient_identity_id = :pid AND code = '8867-4'
                    """
                ),
                {"pid": patient_id},
            )
        ).scalar_one()
    if post.status_code == 403:
        assert after_count == before_count
    else:
        assert post.status_code == 200
        assert after_count == before_count + 1


@requires_db
async def test_concurrent_site_suspend_and_manual_vital_post(db_client, db_engine) -> None:
    clinician, org_admin, patient_id, encounter_id = await _ready_site(db_client, db_engine)
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
        before_count = (
            await connection.execute(
                text("SELECT count(*) FROM observations WHERE patient_identity_id = :pid"),
                {"pid": patient_id},
            )
        ).scalar_one()

    async def suspend_site():
        return await db_client.post(
            (
                f"/api/v1/organizations/{clinician.organization_id}/governance/"
                f"features/{MANUAL_VITALS_FEATURE_ID}/transition"
            ),
            json={"target_state": "SUSPENDED", "expected_row_version": row_version},
            headers=governance_headers(org_admin),
        )

    post, suspend = await asyncio.gather(
        _post_vital(db_client, clinician, patient_id, encounter_id, key=f"mv-site-{uuid4().hex}"),
        suspend_site(),
    )
    assert suspend.status_code == 200
    async with db_engine.connect() as connection:
        after_count = (
            await connection.execute(
                text("SELECT count(*) FROM observations WHERE patient_identity_id = :pid"),
                {"pid": patient_id},
            )
        ).scalar_one()
    if post.status_code == 403:
        assert after_count == before_count
    else:
        assert post.status_code == 200
        assert after_count == before_count + 1


@requires_db
async def test_concurrent_profile_republish_and_manual_vital_post(db_client, db_engine) -> None:
    clinician, org_admin, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    async with db_engine.connect() as connection:
        before_count = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM observations
                    WHERE patient_identity_id = :pid AND code = '8867-4'
                    """
                ),
                {"pid": patient_id},
            )
        ).scalar_one()

    async def republish():
        await republish_manual_vitals_policy(
            db_client,
            org_admin,
            clinician.organization_id,
            approved_measurements=["body_temperature"],
            scope=default_catalog_version_scope_fingerprint(["body_temperature"]),
        )
        return True

    post, _ = await asyncio.gather(
        _post_vital(db_client, clinician, patient_id, encounter_id, key=f"mv-pol-{uuid4().hex}"),
        republish(),
    )
    async with db_engine.connect() as connection:
        after_count = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM observations
                    WHERE patient_identity_id = :pid AND code = '8867-4'
                    """
                ),
                {"pid": patient_id},
            )
        ).scalar_one()
    if post.status_code == 403:
        assert after_count == before_count
    else:
        assert post.status_code == 200
        assert after_count == before_count + 1


@requires_db
async def test_provider_row_lock_blocks_concurrent_suspend(db_engine) -> None:
    capability_id = await seed_manual_vitals_provider(db_engine)
    suspend_started = asyncio.Event()
    suspend_finished = asyncio.Event()
    lock_released = asyncio.Event()

    async def hold_provider_lock() -> None:
        async with db_engine.connect() as connection:
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        SELECT id FROM provider_capabilities
                        WHERE id = :id
                        FOR UPDATE
                        """
                    ),
                    {"id": capability_id},
                )
                suspend_started.set()
                await lock_released.wait()

    async def suspend_while_locked() -> None:
        await suspend_started.wait()
        async with db_engine.connect() as connection:
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        SELECT id FROM provider_capabilities
                        WHERE id = :id
                        FOR UPDATE
                        """
                    ),
                    {"id": capability_id},
                )
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
        suspend_finished.set()

    holder = asyncio.create_task(hold_provider_lock())
    await suspend_started.wait()
    suspender = asyncio.create_task(suspend_while_locked())
    await asyncio.sleep(0.2)
    assert not suspend_finished.is_set()
    lock_released.set()
    await asyncio.wait_for(holder, timeout=5)
    await asyncio.wait_for(suspender, timeout=5)
    assert suspend_finished.is_set()
