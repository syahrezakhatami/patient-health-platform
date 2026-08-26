"""Product access and tenancy foundation.

Revision ID: 20260814_0018
Revises: 20260814_0017
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0018"
down_revision: str | None = "20260814_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PLATFORM_ADMIN_RETAINED = (
    "iam.platform",
    "iam.user.read",
    "iam.user.provision",
    "iam.membership.manage",
    "org.organization.create",
    "org.organization.read",
)


def upgrade() -> None:
    op.create_table(
        "patient_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('ACTIVE','DISABLED')", name="patient_account_status"),
        sa.CheckConstraint("char_length(subject) > 0", name="patient_account_subject_required"),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_patient_accounts_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject", name="uq_patient_accounts_subject"),
    )
    op.create_index(
        "ix_patient_accounts_patient_identity_id",
        "patient_accounts",
        ["patient_identity_id"],
    )
    op.create_index(
        "uq_patient_accounts_active_identity",
        "patient_accounts",
        ["patient_identity_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'patient.account.read', 'Read own patient account'),
            (gen_random_uuid(), 'patient.record.read', 'Read own same-org clinical projection');
        """
    )
    retained = ", ".join(f"'{code}'" for code in _PLATFORM_ADMIN_RETAINED)
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE code = 'PLATFORM_ADMIN')
          AND permission_id NOT IN (
              SELECT id FROM permissions WHERE code IN ({retained})
          );
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_patient_account_rebinding()
        RETURNS trigger AS $$
        DECLARE
            current_id uuid;
            life text;
            nxt uuid;
            hops integer := 0;
            allowed boolean := FALSE;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'patient accounts cannot be deleted';
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id THEN
                RAISE EXCEPTION 'patient account id is immutable';
            END IF;
            IF NEW.subject IS DISTINCT FROM OLD.subject THEN
                RAISE EXCEPTION 'patient account subject is immutable';
            END IF;
            IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'patient account created_at is immutable';
            END IF;
            IF OLD.status = 'DISABLED' AND NEW.status = 'ACTIVE' THEN
                RAISE EXCEPTION 'disabled patient accounts cannot be reactivated';
            END IF;
            IF NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id THEN
                current_id := OLD.patient_identity_id;
                WHILE hops < 8 LOOP
                    SELECT lifecycle_status, surviving_identity_id
                      INTO life, nxt
                      FROM patient_identities
                     WHERE id = current_id;
                    IF NOT FOUND THEN
                        EXIT;
                    END IF;
                    IF life = 'MERGED' AND nxt IS NOT NULL AND nxt IS DISTINCT FROM current_id THEN
                        current_id := nxt;
                        hops := hops + 1;
                        IF current_id = NEW.patient_identity_id THEN
                            allowed := TRUE;
                            EXIT;
                        END IF;
                    ELSE
                        EXIT;
                    END IF;
                END LOOP;
                IF NOT allowed THEN
                    RAISE EXCEPTION
                        'patient account identity may only rebind to canonical survivor';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_patient_accounts_binding_immutable ON patient_accounts;")
    op.execute(
        """
        CREATE TRIGGER trg_patient_accounts_binding_immutable
        BEFORE UPDATE OR DELETE ON patient_accounts
        FOR EACH ROW
        EXECUTE FUNCTION prevent_patient_account_rebinding();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_patient_accounts_binding_immutable ON patient_accounts;")
    op.execute("DROP FUNCTION IF EXISTS prevent_patient_account_rebinding();")
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r
        JOIN permissions p ON (
            p.code LIKE 'clinical.%'
            OR p.code LIKE 'mpi.%'
            OR p.code IN (
                'org.facility.create','org.facility.read','org.identifier.manage'
            )
        )
        WHERE r.code = 'PLATFORM_ADMIN'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions existing
              WHERE existing.role_id = r.id AND existing.permission_id = p.id
          );
        """
    )
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code LIKE 'patient.%');
        """
    )
    op.execute("DELETE FROM permissions WHERE code LIKE 'patient.%';")
    op.drop_index("uq_patient_accounts_active_identity", table_name="patient_accounts")
    op.drop_index("ix_patient_accounts_patient_identity_id", table_name="patient_accounts")
    op.drop_table("patient_accounts")
