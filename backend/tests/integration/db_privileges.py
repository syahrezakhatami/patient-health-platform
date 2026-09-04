"""Development database privilege helpers for integration tests.

Administrative GRANT/REVOKE operations must use DATABASE_MIGRATION_URL (php_admin),
never the app_dml test engine connection.
"""

import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# app_dml lacks DELETE on clinical tables; privilege denial is a valid defense layer.
APP_DML_DELETE_DENIED = r"cannot be deleted|permission denied"
APP_DML_DELETE_OR_FK_DENIED = r"cannot be deleted|foreign key|permission denied"
APP_DML_INSERT_ONLY_DENIED = r"insert-only|permission denied"
PROVENANCE_DELETE_DENIED = r"insert-only|foreign key|permission denied"


def migration_database_url() -> str | None:
    return os.environ.get("DATABASE_MIGRATION_URL")


def _grant_script_statements() -> list[str]:
    script = Path(__file__).resolve().parents[2] / "scripts" / "grant_dev_privileges.sql"
    statements: list[str] = []
    for chunk in script.read_text(encoding="utf-8").split(";"):
        statement = chunk.strip()
        if statement and not statement.startswith("--"):
            statements.append(statement)
    return statements


async def apply_dev_privileges() -> None:
    """Apply scripts/grant_dev_privileges.sql using the migration/admin role."""
    migration_url = migration_database_url()
    if migration_url is None:
        return
    admin_engine = create_async_engine(migration_url, pool_pre_ping=True)
    try:
        async with admin_engine.begin() as connection:
            for statement in _grant_script_statements():
                await connection.execute(text(statement))
            await _sync_governance_role_permissions(connection)
    finally:
        await admin_engine.dispose()


async def _sync_governance_role_permissions(connection) -> None:
    """Align seeded governance role permissions with catalog defaults."""
    await connection.execute(
        text(
            """
            DELETE FROM role_permissions rp
            USING roles r, permissions p
            WHERE rp.role_id = r.id
              AND rp.permission_id = p.id
              AND p.code LIKE 'governance.%'
              AND (
                r.code IN ('CLINICIAN', 'AUDITOR')
                OR (
                  r.code = 'ORG_ADMIN'
                  AND p.code NOT IN (
                    'governance.profile.read',
                    'governance.profile.manage'
                  )
                )
                OR (
                  r.code = 'PLATFORM_ADMIN'
                  AND p.code <> 'governance.provider.manage'
                )
              )
            """
        )
    )
    await connection.execute(
        text(
            """
            INSERT INTO role_permissions (id, role_id, permission_id)
            SELECT gen_random_uuid(), r.id, p.id
            FROM roles r
            JOIN permissions p ON (
                (r.code = 'PLATFORM_ADMIN' AND p.code = 'governance.provider.manage')
                OR (
                    r.code = 'ORG_ADMIN'
                    AND p.code IN ('governance.profile.read', 'governance.profile.manage')
                )
            )
            WHERE NOT EXISTS (
                SELECT 1 FROM role_permissions existing
                WHERE existing.role_id = r.id AND existing.permission_id = p.id
            )
            """
        )
    )


async def restore_clinical_note_idempotency_app_dml_privileges(db_engine: AsyncEngine) -> None:
    """Match scripts/grant_dev_privileges.sql for clinical_note_write_idempotency."""
    del db_engine
    migration_url = migration_database_url()
    if migration_url is None:
        return
    admin_engine = create_async_engine(migration_url, pool_pre_ping=True)
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(
                text(
                    "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE "
                    "clinical_note_write_idempotency FROM app_dml"
                )
            )
            await connection.execute(
                text("GRANT INSERT, SELECT ON TABLE clinical_note_write_idempotency TO app_dml")
            )
    finally:
        await admin_engine.dispose()


async def restore_clinical_observation_idempotency_app_dml_privileges(
    db_engine: AsyncEngine,
) -> None:
    """Match scripts/grant_dev_privileges.sql for clinical_observation_write_idempotency."""
    del db_engine
    migration_url = migration_database_url()
    if migration_url is None:
        return
    admin_engine = create_async_engine(migration_url, pool_pre_ping=True)
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(
                text(
                    "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE "
                    "clinical_observation_write_idempotency FROM app_dml"
                )
            )
            await connection.execute(
                text(
                    "GRANT INSERT, SELECT ON TABLE "
                    "clinical_observation_write_idempotency TO app_dml"
                )
            )
    finally:
        await admin_engine.dispose()


async def restore_governance_app_dml_privileges(db_engine: AsyncEngine) -> None:
    """Match scripts/grant_dev_privileges.sql for OGP tables."""
    del db_engine
    migration_url = migration_database_url()
    if migration_url is None:
        return
    admin_engine = create_async_engine(migration_url, pool_pre_ping=True)
    try:
        async with admin_engine.begin() as connection:
            statements = (
                (
                    "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE "
                    "governance_admin_idempotency FROM app_dml"
                ),
                (
                    "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE "
                    "governance_approval_evidence FROM app_dml"
                ),
                (
                    "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE "
                    "organization_governance_profile_versions FROM app_dml"
                ),
                "GRANT INSERT, SELECT ON TABLE governance_admin_idempotency TO app_dml",
                "GRANT INSERT, SELECT ON TABLE governance_approval_evidence TO app_dml",
                (
                    "GRANT INSERT, SELECT, UPDATE ON TABLE "
                    "organization_governance_profile_versions TO app_dml"
                ),
                (
                    "GRANT SELECT, INSERT, UPDATE ON TABLE "
                    "organization_governance_profiles TO app_dml"
                ),
                (
                    "GRANT SELECT, INSERT, UPDATE ON TABLE "
                    "organization_feature_activations TO app_dml"
                ),
                (
                    "GRANT SELECT, INSERT, UPDATE ON TABLE "
                    "organization_deployment_gate_states TO app_dml"
                ),
                "GRANT SELECT, INSERT, UPDATE ON TABLE provider_capabilities TO app_dml",
                ("GRANT SELECT, INSERT ON TABLE provider_capability_required_gates TO app_dml"),
            )
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await admin_engine.dispose()
