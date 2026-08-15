"""Wave 2B.4 native immunizations.

Revision ID: 20260814_0013
Revises: 20260814_0012
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0013"
down_revision: str | None = "20260814_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "immunizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("code_system", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("code_display", sa.String(length=255), nullable=True),
        sa.Column("occurrence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("route", sa.String(length=32), nullable=True),
        sa.Column("site", sa.String(length=32), nullable=True),
        sa.Column("note_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "category IN ('ADMINISTERED','REPORTED')",
            name="immunization_category",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','AMENDED','ENTERED_IN_ERROR')",
            name="immunization_status",
        ),
        sa.CheckConstraint(
            "route IS NULL OR route IN ('IM','SC','ORAL','INTRANASAL','OTHER')",
            name="immunization_route",
        ),
        sa.CheckConstraint(
            "site IS NULL OR site IN ("
            "'LEFT_ARM','RIGHT_ARM','LEFT_THIGH','RIGHT_THIGH','OTHER'"
            ")",
            name="immunization_site",
        ),
        sa.CheckConstraint("char_length(code_system) > 0", name="immunization_code_system_required"),
        sa.CheckConstraint("char_length(code) > 0", name="immunization_code_required"),
        sa.CheckConstraint("version >= 1", name="immunization_version_positive"),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_immunizations_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_immunizations_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_immunizations_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_immunizations_facility_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["clinical_provenances.id"],
            name="fk_immunizations_provenance_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_immunizations"),
    )
    op.create_index(
        "ix_immunizations_patient_identity_id", "immunizations", ["patient_identity_id"]
    )
    op.create_index("ix_immunizations_encounter_id", "immunizations", ["encounter_id"])
    op.create_index("ix_immunizations_organization_id", "immunizations", ["organization_id"])
    op.create_index("ix_immunizations_recorded_at", "immunizations", ["recorded_at"])

    op.execute(
        "ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS clinical_provenance_subject;"
    )
    op.execute(
        "ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS "
        "ck_clinical_provenances_clinical_provenance_subject;"
    )
    op.execute(
        """
        ALTER TABLE clinical_provenances
        ADD CONSTRAINT clinical_provenance_subject CHECK (
            subject_type IN (
                'ENCOUNTER','CLINICAL_NOTE','CONDITION','OBSERVATION',
                'LABORATORY_ORDER','LABORATORY_SPECIMEN','LABORATORY_RESULT',
                'MEDICATION','ALLERGY','CONSENT','IMMUNIZATION'
            )
        );
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_immunization_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'immunizations cannot be deleted';
            END IF;
            IF NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id
               OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
               OR NEW.category IS DISTINCT FROM OLD.category
               OR NEW.code_system IS DISTINCT FROM OLD.code_system
               OR NEW.code IS DISTINCT FROM OLD.code
               OR NEW.code_display IS DISTINCT FROM OLD.code_display
               OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
               OR NEW.recorder_id IS DISTINCT FROM OLD.recorder_id
               OR NEW.provenance_id IS DISTINCT FROM OLD.provenance_id THEN
                RAISE EXCEPTION 'immunization historical facts are immutable';
            END IF;
            IF OLD.status = 'ENTERED_IN_ERROR' THEN
                RAISE EXCEPTION 'entered-in-error immunization is immutable';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status
               AND NOT (
                    (OLD.status = 'ACTIVE' AND NEW.status IN ('AMENDED','ENTERED_IN_ERROR'))
                    OR (OLD.status = 'AMENDED' AND NEW.status = 'ENTERED_IN_ERROR')
               ) THEN
                RAISE EXCEPTION 'invalid immunization status transition';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_immunizations_history_immutable
        BEFORE UPDATE OR DELETE ON immunizations
        FOR EACH ROW
        EXECUTE FUNCTION prevent_immunization_history_mutation();
        """
    )

    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'clinical.immunization.create', 'Create immunizations'),
            (gen_random_uuid(), 'clinical.immunization.read', 'Read immunizations'),
            (gen_random_uuid(), 'clinical.immunization.update', 'Amend immunizations'),
            (
                gen_random_uuid(),
                'clinical.immunization.entered_in_error',
                'Mark immunizations entered in error'
            );
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r
        JOIN permissions p ON (
            (
                r.code IN ('PLATFORM_ADMIN','CLINICIAN')
                AND p.code LIKE 'clinical.immunization.%'
            )
            OR (
                r.code IN ('ORG_ADMIN','AUDITOR')
                AND p.code = 'clinical.immunization.read'
            )
        )
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permissions existing
            WHERE existing.role_id = r.id AND existing.permission_id = p.id
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT id FROM permissions WHERE code LIKE 'clinical.immunization.%'
        );
        """
    )
    op.execute("DELETE FROM permissions WHERE code LIKE 'clinical.immunization.%';")
    op.execute("DROP TRIGGER IF EXISTS trg_immunizations_history_immutable ON immunizations;")
    op.execute("DROP FUNCTION IF EXISTS prevent_immunization_history_mutation();")
    op.execute(
        "ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS clinical_provenance_subject;"
    )
    op.execute(
        "ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS "
        "ck_clinical_provenances_clinical_provenance_subject;"
    )
    op.execute(
        """
        ALTER TABLE clinical_provenances
        ADD CONSTRAINT clinical_provenance_subject CHECK (
            subject_type IN (
                'ENCOUNTER','CLINICAL_NOTE','CONDITION','OBSERVATION',
                'LABORATORY_ORDER','LABORATORY_SPECIMEN','LABORATORY_RESULT',
                'MEDICATION','ALLERGY','CONSENT'
            )
        );
        """
    )
    op.drop_index("ix_immunizations_recorded_at", table_name="immunizations")
    op.drop_index("ix_immunizations_organization_id", table_name="immunizations")
    op.drop_index("ix_immunizations_encounter_id", table_name="immunizations")
    op.drop_index("ix_immunizations_patient_identity_id", table_name="immunizations")
    op.drop_table("immunizations")
