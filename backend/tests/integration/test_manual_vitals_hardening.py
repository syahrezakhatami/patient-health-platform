import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.clinical.domain.manual_vitals_approval import (
    default_catalog_version_scope_fingerprint,
)
from app.modules.clinical.domain.vital_signs_catalog import MANUAL_VITALS_FEATURE_ID
from app.modules.governance.domain.enums import PolicyEffect
from app.shared.types.ids import new_id
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.integration.conftest import DATABASE_URL, requires_db, seed_actor
from tests.integration.db_privileges import (
    apply_dev_privileges,
    migration_database_url,
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
from tests.integration.test_clinical_note_write import (
    _seed_facility,
    _seed_facility_clinician,
)
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter

pytestmark = [pytest.mark.integration, requires_db]

BACKEND_ROOT = Path(__file__).resolve().parents[2]
HEART_ONLY_SCOPE = default_catalog_version_scope_fingerprint(["heart_rate"])
APP_DML_URL = os.environ.get(
    "APP_DML_DATABASE_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


@pytest.fixture(autouse=True)
async def _manual_vitals_hardening_privileges(db_engine) -> None:
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
    return clinician, patient_id, encounter_id


async def _post_vital(
    db_client,
    clinician,
    patient_id,
    encounter_id,
    *,
    key: str | None = None,
    **body_kwargs,
):
    return await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(
            clinician,
            idempotency_key=key or f"mv-{uuid4().hex}",
        ),
        json=create_manual_vital_body(patient_id, encounter_id, **body_kwargs),
    )


async def _set_encounter_status(db_client, clinician, encounter_id: str, status: str) -> None:
    response = await db_client.post(
        f"/api/v1/clinical/encounters/{encounter_id}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": status},
    )
    assert response.status_code == 200, response.text


def test_migration_0021_ddl_only_without_provider_seed_or_grants() -> None:
    migration = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "20260814_0021_clinical_observation_write_idempotency.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20260814_0020"' in migration
    assert "clinical_observation_write_idempotency" in migration
    assert "prevent_clinical_observation_write_idempotency_mutation" in migration
    assert "GRANT " not in migration
    assert "provider_capabilities" not in migration
    assert "manual_vital_signs_write" not in migration
    assert 'op.drop_table("clinical_observation_write_idempotency")' in migration


@requires_db
async def test_production_dark_fail_closed_without_site_activation(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    get_resp = await db_client.get(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician),
    )
    assert get_resp.status_code == 200
    assert get_resp.json() == {
        "available": False,
        "catalog_version": None,
        "feature_version": None,
        "measurements": [],
    }
    async with db_engine.connect() as connection:
        before_obs = (
            await connection.execute(text("SELECT count(*) FROM observations"))
        ).scalar_one()
        before_idem = (
            await connection.execute(
                text("SELECT count(*) FROM clinical_observation_write_idempotency")
            )
        ).scalar_one()
    post_resp = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(
            clinician,
            idempotency_key=f"mv-empty-reg-{uuid4().hex}",
        ),
        json=create_manual_vital_body(new_id(), new_id()),
    )
    assert post_resp.status_code == 403
    assert post_resp.json()["error"]["code"] == "manual_vital_signs_unavailable"
    async with db_engine.connect() as connection:
        after_obs = (
            await connection.execute(text("SELECT count(*) FROM observations"))
        ).scalar_one()
        after_idem = (
            await connection.execute(
                text("SELECT count(*) FROM clinical_observation_write_idempotency")
            )
        ).scalar_one()
    assert after_obs == before_obs
    assert after_idem == before_idem


@requires_db
async def test_observation_idempotency_app_dml_privileges(db_engine) -> None:
    await restore_clinical_observation_idempotency_app_dml_privileges(db_engine)
    async with db_engine.connect() as connection:
        version = await connection.execute(text("SELECT version_num FROM alembic_version"))
        assert version.scalar_one() == "20260814_0021"
        table_exists = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'clinical_observation_write_idempotency'
                    """
                )
            )
        ).scalar_one()
        constraint = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM pg_constraint
                    WHERE conname = 'uq_clinical_observation_write_idempotency_scope'
                    """
                )
            )
        ).scalar_one()
        trigger = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM pg_trigger
                    WHERE tgname = 'trg_clinical_observation_write_idempotency_immutable'
                    """
                )
            )
        ).scalar_one()
        privileges = await connection.execute(
            text(
                """
                SELECT privilege_type FROM information_schema.role_table_grants
                WHERE grantee = 'app_dml'
                  AND table_name = 'clinical_observation_write_idempotency'
                """
            )
        )
        granted = {row[0] for row in privileges}
    assert table_exists == 1
    assert constraint == 1
    assert trigger == 1
    assert granted == {"INSERT", "SELECT"}


@requires_db
async def test_app_dml_database_role_used(db_engine) -> None:
    assert DATABASE_URL is not None
    assert "app_dml" in DATABASE_URL
    async with db_engine.connect() as connection:
        role = (await connection.execute(text("SELECT current_user"))).scalar_one()
    assert role == "app_dml"


@requires_db
async def test_zz_migration_0021_downgrade_upgrade_roundtrip(db_engine) -> None:
    env = os.environ.copy()
    url = (
        env.get("DATABASE_MIGRATION_URL") or env.get("TEST_DATABASE_URL") or env.get("DATABASE_URL")
    )
    assert url
    env["DATABASE_MIGRATION_URL"] = url
    env["DATABASE_URL"] = url

    def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    try:
        downgrade = await asyncio.to_thread(run_alembic, "downgrade", "20260814_0020")
        assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
        async with db_engine.connect() as connection:
            version = await connection.execute(text("SELECT version_num FROM alembic_version"))
            assert version.scalar_one() == "20260814_0020"
            missing = (
                await connection.execute(
                    text(
                        """
                        SELECT count(*) FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'clinical_observation_write_idempotency'
                        """
                    )
                )
            ).scalar_one()
        assert missing == 0
    finally:
        upgrade = await asyncio.to_thread(run_alembic, "upgrade", "20260814_0021")
        assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    await apply_dev_privileges()
    async with db_engine.connect() as connection:
        version = await connection.execute(text("SELECT version_num FROM alembic_version"))
        assert version.scalar_one() == "20260814_0021"
        heads = await connection.execute(text("SELECT count(*) FROM alembic_version"))
        assert heads.scalar_one() == 1
        restored = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'clinical_observation_write_idempotency'
                    """
                )
            )
        ).scalar_one()
        provider_count = (
            await connection.execute(text("SELECT count(*) FROM provider_capabilities"))
        ).scalar_one()
    assert restored == 1
    assert provider_count >= 0


@requires_db
async def test_cross_org_manual_vitals_concealed(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    actor_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    actor_b_clinician, registrar_b, org_admin_b = await _seed_clinician_with_governance(db_engine)
    patient_b = await _active_patient(db_client, registrar_b)
    encounter_b = (await _open_encounter(db_client, actor_b_clinician, patient_b)).json()["id"]
    await activate_manual_vitals_site(
        db_client,
        org_admin_b,
        actor_b_clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    get_cross = await db_client.get(
        manual_vitals_path(actor_b_clinician.organization_id),
        headers=manual_vitals_write_headers(actor_a),
    )
    assert get_cross.status_code == 404
    post_cross = await db_client.post(
        manual_vitals_path(actor_b_clinician.organization_id),
        headers=manual_vitals_write_headers(actor_a, idempotency_key=f"mv-xorg-{uuid4().hex}"),
        json=create_manual_vital_body(patient_b, encounter_b),
    )
    assert post_cross.status_code == 404
    assert str(actor_b_clinician.organization_id) not in post_cross.text


@requires_db
async def test_cross_org_approval_does_not_authorize(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    org_a_clinician, registrar_a, org_admin_a = await _seed_clinician_with_governance(db_engine)
    org_b_clinician, registrar_b, org_admin_b = await _seed_clinician_with_governance(db_engine)
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
    ok_a = await _post_vital(db_client, org_a_clinician, patient_a, encounter_a)
    assert ok_a.status_code == 200, ok_a.text
    denied_b = await _post_vital(
        db_client,
        org_a_clinician,
        patient_b,
        encounter_b,
        key=f"mv-xappr-{uuid4().hex}",
    )
    assert denied_b.status_code == 404


@requires_db
async def test_profile_version_binding_denies_stale_approval(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    clinician, registrar, org_admin = await _seed_clinician_with_governance(db_engine)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    first = await db_client.post(
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
            "reason": "Version one",
        },
        headers=governance_headers(org_admin, idempotency_key=f"mv-v1-{new_id().hex[:8]}"),
    )
    assert first.status_code == 200
    version_one = first.json()["id"]
    publish_one = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/profile/versions/{version_one}/publish",
        headers=governance_headers(org_admin, idempotency_key=f"mv-pub1-{new_id().hex[:8]}"),
    )
    assert publish_one.status_code == 200
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
            "scope": HEART_ONLY_SCOPE,
            "decision_by_name": "Dr Example",
            "approval_date": datetime.now(UTC).date().isoformat(),
        },
        headers=governance_headers(org_admin, idempotency_key=f"mv-appr1-{new_id().hex[:8]}"),
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
    second = await db_client.post(
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
            "reason": "Version two",
        },
        headers=governance_headers(org_admin, idempotency_key=f"mv-v2-{new_id().hex[:8]}"),
    )
    assert second.status_code == 200
    version_two = second.json()["id"]
    publish_two = await db_client.post(
        f"/api/v1/organizations/{clinician.organization_id}/governance/profile/versions/{version_two}/publish",
        headers=governance_headers(org_admin, idempotency_key=f"mv-pub2-{new_id().hex[:8]}"),
    )
    assert publish_two.status_code == 200
    denied = await _post_vital(db_client, clinician, patient_id, encounter_id)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "manual_vital_signs_unavailable"


@requires_db
async def test_wrong_patient_matrix(db_client, db_engine) -> None:
    clinician, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    other_registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    other_patient = await _active_patient(db_client, other_registrar)
    wrong = await _post_vital(
        db_client,
        clinician,
        other_patient,
        encounter_id,
        key=f"mv-wp-{uuid4().hex}",
    )
    assert wrong.status_code == 404
    assert wrong.json()["error"]["code"] == "not_found"
    foreign = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    foreign_patient = await _active_patient(db_client, foreign)
    cross = await _post_vital(
        db_client,
        clinician,
        foreign_patient,
        encounter_id,
        key=f"mv-wp2-{uuid4().hex}",
    )
    assert cross.status_code == 404


@requires_db
async def test_merged_identity_persists_historical_patient(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    clinician, registrar, org_admin = await _seed_clinician_with_governance(db_engine)
    officer = await seed_actor(
        db_engine,
        role_code=RoleCode.IDENTITY_OFFICER,
        organization_id=clinician.organization_id,
    )
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Merge",
            "family_name": "Source",
            "birth_date": "1977-07-07",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("MV"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Merge", family="Survivor", birth="1977-07-07"),
    )
    source_id = source.json()["id"]
    survivor_id = survivor.json()["id"]
    historical = await _open_encounter(db_client, clinician, source_id)
    encounter_id = historical.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source_id,
            "target_identity_id": survivor_id,
            "reason": "Manual vitals historical encounter",
            "evidence": merge_evidence("mv-merge"),
        },
    )
    assert merged.status_code in {200, 201}
    await activate_manual_vitals_site(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    created = await _post_vital(
        db_client,
        clinician,
        survivor_id,
        encounter_id,
        key=f"mv-mpi-{uuid4().hex}",
    )
    assert created.status_code == 200, created.text
    assert created.json()["patient_identity_id"] == source_id


@requires_db
async def test_retired_identity_denies(db_client, db_engine) -> None:
    clinician, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": patient_id},
        )
    denied = await _post_vital(
        db_client,
        clinician,
        patient_id,
        encounter_id,
        key=f"mv-ret-{uuid4().hex}",
    )
    assert denied.status_code == 409


@requires_db
async def test_facility_matrix(db_client, db_engine) -> None:
    await seed_manual_vitals_provider(db_engine)
    clinician, registrar, org_admin = await _seed_clinician_with_governance(db_engine)
    facility_a = await _seed_facility(db_engine, clinician.organization_id, "MVA")
    facility_b = await _seed_facility(db_engine, clinician.organization_id, "MVB")
    bound_a = await _seed_facility_clinician(db_engine, clinician.organization_id, facility_a)
    patient_id = await _active_patient(db_client, registrar)
    encounter = await db_client.post(
        "/api/v1/clinical/encounters",
        headers=manual_vitals_write_headers(clinician, facility_id=facility_a),
        json={"patient_identity_id": patient_id, "encounter_class": "AMB"},
    )
    encounter_id = encounter.json()["id"]
    await activate_manual_vitals_site(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=["heart_rate"],
        scope=HEART_ONLY_SCOPE,
    )
    match = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(
            bound_a,
            facility_id=facility_a,
            idempotency_key=f"mv-fac-a-{uuid4().hex}",
        ),
        json=create_manual_vital_body(patient_id, encounter_id),
    )
    assert match.status_code == 200, match.text
    assert match.json()["facility_id"] == str(facility_a)
    mismatch = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(
            bound_a,
            facility_id=facility_b,
            idempotency_key=f"mv-fac-b-{uuid4().hex}",
        ),
        json=create_manual_vital_body(patient_id, encounter_id),
    )
    assert mismatch.status_code == 403
    inherit = await _post_vital(db_client, clinician, patient_id, encounter_id)
    assert inherit.status_code == 200
    assert inherit.json()["facility_id"] == str(facility_a)


@requires_db
async def test_encounter_status_matrix(db_client, db_engine) -> None:
    clinician, patient_id, planned_enc = await _ready_site(
        db_client, db_engine, planned=PolicyEffect.ALLOW
    )
    assert (await _post_vital(db_client, clinician, patient_id, planned_enc)).status_code == 200

    clinician, patient_id, planned_deny_enc = await _ready_site(
        db_client, db_engine, planned=PolicyEffect.DENY
    )
    denied_planned = await _post_vital(db_client, clinician, patient_id, planned_deny_enc)
    assert denied_planned.status_code == 409
    assert denied_planned.json()["error"]["code"] == "encounter_not_documentable"

    clinician, patient_id, in_progress_enc = await _ready_site(
        db_client, db_engine, planned=PolicyEffect.DENY
    )
    await _set_encounter_status(db_client, clinician, in_progress_enc, "IN_PROGRESS")
    assert (await _post_vital(db_client, clinician, patient_id, in_progress_enc)).status_code == 200

    clinician, patient_id, finished_deny_enc = await _ready_site(
        db_client, db_engine, finished=PolicyEffect.DENY, late_doc=False
    )
    await _set_encounter_status(db_client, clinician, finished_deny_enc, "IN_PROGRESS")
    await _set_encounter_status(db_client, clinician, finished_deny_enc, "FINISHED")
    denied_finished = await _post_vital(db_client, clinician, patient_id, finished_deny_enc)
    assert denied_finished.status_code == 409

    clinician, patient_id, finished_late_enc = await _ready_site(
        db_client, db_engine, finished=PolicyEffect.DENY, late_doc=True
    )
    await _set_encounter_status(db_client, clinician, finished_late_enc, "IN_PROGRESS")
    await _set_encounter_status(db_client, clinician, finished_late_enc, "FINISHED")
    late = await _post_vital(db_client, clinician, patient_id, finished_late_enc)
    assert late.status_code == 200

    clinician, patient_id, cancelled_enc = await _ready_site(db_client, db_engine)
    await _set_encounter_status(db_client, clinician, cancelled_enc, "CANCELLED")
    assert (await _post_vital(db_client, clinician, patient_id, cancelled_enc)).status_code == 409

    clinician, patient_id, eie_enc = await _ready_site(db_client, db_engine)
    await _set_encounter_status(db_client, clinician, eie_enc, "ENTERED_IN_ERROR")
    assert (await _post_vital(db_client, clinician, patient_id, eie_enc)).status_code == 409


@requires_db
async def test_idempotency_replay_requires_current_permission(db_client, db_engine) -> None:
    clinician, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    key = f"mv-perm-{uuid4().hex}"
    created = await _post_vital(db_client, clinician, patient_id, encounter_id, key=key)
    assert created.status_code == 200
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
    replay = await _post_vital(db_client, clinician, patient_id, encounter_id, key=key)
    assert replay.status_code == 403


@requires_db
async def test_idempotency_replay_denies_when_provider_suspended(db_client, db_engine) -> None:
    capability_id = await seed_manual_vitals_provider(db_engine)
    clinician, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    key = f"mv-susp-replay-{uuid4().hex}"
    created = await _post_vital(db_client, clinician, patient_id, encounter_id, key=key)
    assert created.status_code == 200
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
    replay = await _post_vital(db_client, clinician, patient_id, encounter_id, key=key)
    assert replay.status_code == 403


@requires_db
async def test_idempotency_replay_denies_when_site_policy_excludes_measurement(
    db_client, db_engine
) -> None:
    clinician, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    key = f"mv-pol-replay-{uuid4().hex}"
    created = await _post_vital(db_client, clinician, patient_id, encounter_id, key=key)
    assert created.status_code == 200
    org_admin = await seed_governance_actor_for_organization(
        db_engine,
        clinician.organization_id,
        permissions=frozenset(
            {
                Permission.GOVERNANCE_PROFILE_MANAGE,
                Permission.GOVERNANCE_APPROVAL_RECORD,
            }
        ),
    )
    temp_scope = default_catalog_version_scope_fingerprint(["body_temperature"])
    await republish_manual_vitals_policy(
        db_client,
        org_admin,
        clinician.organization_id,
        approved_measurements=["body_temperature"],
        scope=temp_scope,
    )
    replay = await _post_vital(db_client, clinician, patient_id, encounter_id, key=key)
    assert replay.status_code == 403


@requires_db
async def test_concurrent_different_keys_create_two_observations(db_client, db_engine) -> None:
    clinician, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    left, right = await asyncio.gather(
        _post_vital(
            db_client,
            clinician,
            patient_id,
            encounter_id,
            key=f"mv-dk1-{uuid4().hex}",
            value="71",
        ),
        _post_vital(
            db_client,
            clinician,
            patient_id,
            encounter_id,
            key=f"mv-dk2-{uuid4().hex}",
            value="72",
        ),
    )
    assert left.status_code == 200
    assert right.status_code == 200
    assert left.json()["id"] != right.json()["id"]


@requires_db
async def test_concurrent_same_key_exact_row_counts(db_client, db_engine) -> None:
    clinician, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    key = f"mv-race-counts-{uuid4().hex}"
    body = create_manual_vital_body(patient_id, encounter_id, value="72")
    headers = manual_vitals_write_headers(clinician, idempotency_key=key)

    async def post_once():
        return await db_client.post(
            manual_vitals_path(clinician.organization_id),
            headers=headers,
            json=body,
        )

    left, right = await asyncio.gather(post_once(), post_once())
    assert left.status_code == 200
    assert right.status_code == 200
    assert left.json()["id"] == right.json()["id"]
    observation_id = left.json()["id"]
    async with db_engine.connect() as connection:
        obs_count = (
            await connection.execute(
                text("SELECT count(*) FROM observations WHERE id = :id"),
                {"id": observation_id},
            )
        ).scalar_one()
        idem_count = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM clinical_observation_write_idempotency
                    WHERE idempotency_key = :key
                    """
                ),
                {"key": key},
            )
        ).scalar_one()
        audit_count = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM audit_events
                    WHERE resource_id = :id AND action = 'OBSERVATION_CREATED'
                    """
                ),
                {"id": observation_id},
            )
        ).scalar_one()
    assert obs_count == 1
    assert idem_count == 1
    assert audit_count == 1


@requires_db
async def test_post_extra_fields_forbidden(db_client, db_engine) -> None:
    clinician, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    body = create_manual_vital_body(patient_id, encounter_id)
    body["loinc"] = "8867-4"
    body["unit"] = "/min"
    body["category"] = "VITAL_SIGNS"
    body["status"] = "FINAL"
    body["recorded_at"] = datetime.now(UTC).isoformat()
    body["provider_catalog_version"] = "manual-vitals-mvp-v1"
    body["site_approved"] = True
    body["approval_id"] = str(new_id())
    response = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(
            clinician,
            idempotency_key=f"mv-extra-{uuid4().hex}",
        ),
        json=body,
    )
    assert response.status_code == 422


@requires_db
async def test_success_audit_and_provenance_metadata(db_client, db_engine) -> None:
    clinician, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    response = await _post_vital(
        db_client,
        clinician,
        patient_id,
        encounter_id,
        key=f"mv-audit-{uuid4().hex}",
    )
    assert response.status_code == 200, response.text
    observation_id = response.json()["id"]
    async with db_engine.connect() as connection:
        observation = (
            await connection.execute(
                text(
                    """
                    SELECT recorder_id, provenance_id, patient_identity_id
                    FROM observations WHERE id = :id
                    """
                ),
                {"id": observation_id},
            )
        ).one()
        audit = (
            await connection.execute(
                text(
                    """
                    SELECT action, metadata FROM audit_events
                    WHERE resource_id = :id AND action = 'OBSERVATION_CREATED'
                    """
                ),
                {"id": observation_id},
            )
        ).one()
    assert observation.recorder_id == clinician.user_id
    assert observation.provenance_id is not None
    assert audit.action == "OBSERVATION_CREATED"
    metadata = audit.metadata
    assert metadata["feature_id"] == MANUAL_VITALS_FEATURE_ID
    assert metadata["catalog_version"] == "manual-vitals-mvp-v1"
    assert metadata["measurement_key"] == "heart_rate"
    assert "governance_profile_version_id" in metadata


@requires_db
async def test_zz_audit_failure_rolls_back_observation(db_client, db_engine) -> None:
    migration_url = migration_database_url()
    if migration_url is None:
        pytest.skip("DATABASE_MIGRATION_URL required for audit rollback test")
    clinician, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    admin_engine = create_async_engine(migration_url, pool_pre_ping=True)
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(text("REVOKE INSERT ON TABLE audit_events FROM app_dml"))
        async with db_engine.connect() as connection:
            before_obs = (
                await connection.execute(text("SELECT count(*) FROM observations"))
            ).scalar_one()
            before_idem = (
                await connection.execute(
                    text("SELECT count(*) FROM clinical_observation_write_idempotency")
                )
            ).scalar_one()
        response = None
        try:
            response = await _post_vital(
                db_client,
                clinician,
                patient_id,
                encounter_id,
                key=f"mv-audit-fail-{uuid4().hex}",
            )
        except Exception:
            response = None
        if response is not None:
            assert response.status_code >= 400
        async with db_engine.connect() as connection:
            after_obs = (
                await connection.execute(text("SELECT count(*) FROM observations"))
            ).scalar_one()
            after_idem = (
                await connection.execute(
                    text("SELECT count(*) FROM clinical_observation_write_idempotency")
                )
            ).scalar_one()
        assert after_obs == before_obs
        assert after_idem == before_idem
    finally:
        await admin_engine.dispose()
        await apply_dev_privileges()


@requires_db
async def test_effective_at_timezone_semantic_replay(db_client, db_engine) -> None:
    clinician, patient_id, encounter_id = await _ready_site(db_client, db_engine)
    key = f"mv-tz-{uuid4().hex}"
    instant = datetime(2026, 8, 29, 10, 0, tzinfo=timezone(timedelta(hours=7)))
    first = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician, idempotency_key=key),
        json=create_manual_vital_body(
            patient_id,
            encounter_id,
            value="72",
            effective_at=instant.isoformat(),
        ),
    )
    second = await db_client.post(
        manual_vitals_path(clinician.organization_id),
        headers=manual_vitals_write_headers(clinician, idempotency_key=key),
        json=create_manual_vital_body(
            patient_id,
            encounter_id,
            value="72",
            effective_at=instant.astimezone(UTC).isoformat(),
        ),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


@requires_db
async def test_governance_actor_helpers_remain_org_scoped(db_engine) -> None:
    actor_a = await seed_governance_actor(
        db_engine,
        permissions=frozenset({Permission.GOVERNANCE_PROFILE_READ}),
    )
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    actor_b = await seed_governance_actor_for_organization(
        db_engine,
        clinician.organization_id,
        permissions=frozenset({Permission.GOVERNANCE_PROFILE_READ}),
    )
    assert actor_a.organization_id != actor_b.organization_id
