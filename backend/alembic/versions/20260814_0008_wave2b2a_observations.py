"""Wave 2B.2a native observations.

Revision ID: 20260814_0008
Revises: 20260814_0007
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0008"
down_revision: str | None = "20260814_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("code_system", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("code_display", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("value_type", sa.String(length=16), nullable=False),
        sa.Column("value_numeric", sa.Numeric(14, 4), nullable=True),
        sa.Column("value_text", sa.String(length=2000), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("value_code_system", sa.String(length=128), nullable=True),
        sa.Column("value_code", sa.String(length=64), nullable=True),
        sa.Column("value_code_display", sa.String(length=255), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("reference_range_low", sa.Numeric(14, 4), nullable=True),
        sa.Column("reference_range_high", sa.Numeric(14, 4), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "category IN ('VITAL_SIGNS','EXAM','OTHER')",
            name="observation_category",
        ),
        sa.CheckConstraint(
            "status IN ('FINAL','AMENDED','ENTERED_IN_ERROR')",
            name="observation_status",
        ),
        sa.CheckConstraint(
            "value_type IN ('NUMERIC','TEXT','BOOLEAN','CODED')",
            name="observation_value_type",
        ),
        sa.CheckConstraint("char_length(code_system) > 0", name="observation_code_system_required"),
        sa.CheckConstraint("char_length(code) > 0", name="observation_code_required"),
        sa.CheckConstraint("version >= 1", name="observation_version_positive"),
        sa.CheckConstraint(
            """
            (
                value_type = 'NUMERIC'
                AND value_numeric IS NOT NULL
                AND value_text IS NULL
                AND value_boolean IS NULL
                AND value_code IS NULL
                AND value_code_system IS NULL
                AND char_length(unit) > 0
            ) OR (
                value_type = 'TEXT'
                AND char_length(value_text) > 0
                AND value_numeric IS NULL
                AND value_boolean IS NULL
                AND value_code IS NULL
                AND value_code_system IS NULL
                AND unit IS NULL
                AND reference_range_low IS NULL
                AND reference_range_high IS NULL
            ) OR (
                value_type = 'BOOLEAN'
                AND value_boolean IS NOT NULL
                AND value_numeric IS NULL
                AND value_text IS NULL
                AND value_code IS NULL
                AND value_code_system IS NULL
                AND unit IS NULL
                AND reference_range_low IS NULL
                AND reference_range_high IS NULL
            ) OR (
                value_type = 'CODED'
                AND char_length(value_code_system) > 0
                AND char_length(value_code) > 0
                AND value_numeric IS NULL
                AND value_text IS NULL
                AND value_boolean IS NULL
                AND unit IS NULL
                AND reference_range_low IS NULL
                AND reference_range_high IS NULL
            )
            """,
            name="observation_value_shape",
        ),
        sa.CheckConstraint(
            "reference_range_low IS NULL OR reference_range_high IS NULL "
            "OR reference_range_high >= reference_range_low",
            name="observation_reference_range",
        ),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_observations_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_observations_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_observations_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_observations_facility_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["clinical_provenances.id"],
            name="fk_observations_provenance_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_observations"),
    )
    op.create_index("ix_observations_patient_identity_id", "observations", ["patient_identity_id"])
    op.create_index("ix_observations_encounter_id", "observations", ["encounter_id"])
    op.create_index("ix_observations_organization_id", "observations", ["organization_id"])
    op.create_index("ix_observations_recorded_at", "observations", ["recorded_at"])

    op.execute("ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS clinical_provenance_subject;")
    op.execute(
        "ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS "
        "ck_clinical_provenances_clinical_provenance_subject;"
    )
    op.execute(
        """
        ALTER TABLE clinical_provenances
        ADD CONSTRAINT clinical_provenance_subject CHECK (
            subject_type IN ('ENCOUNTER','CLINICAL_NOTE','CONDITION','OBSERVATION')
        );
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_observation_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'observations cannot be deleted';
            END IF;
            IF NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id
               OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
               OR NEW.category IS DISTINCT FROM OLD.category
               OR NEW.code_system IS DISTINCT FROM OLD.code_system
               OR NEW.code IS DISTINCT FROM OLD.code
               OR NEW.code_display IS DISTINCT FROM OLD.code_display
               OR NEW.value_type IS DISTINCT FROM OLD.value_type
               OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
               OR NEW.recorder_id IS DISTINCT FROM OLD.recorder_id
               OR NEW.provenance_id IS DISTINCT FROM OLD.provenance_id THEN
                RAISE EXCEPTION 'observation historical facts are immutable';
            END IF;
            IF OLD.status = 'ENTERED_IN_ERROR' THEN
                RAISE EXCEPTION 'entered-in-error observation is immutable';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status
               AND NOT (
                    (OLD.status = 'FINAL' AND NEW.status IN ('AMENDED','ENTERED_IN_ERROR'))
                    OR (OLD.status = 'AMENDED' AND NEW.status = 'ENTERED_IN_ERROR')
               ) THEN
                RAISE EXCEPTION 'invalid observation status transition';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_observations_history_immutable
        BEFORE UPDATE OR DELETE ON observations
        FOR EACH ROW
        EXECUTE FUNCTION prevent_observation_history_mutation();
        """
    )

    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'clinical.observation.create', 'Create observations'),
            (gen_random_uuid(), 'clinical.observation.read', 'Read observations'),
            (gen_random_uuid(), 'clinical.observation.update', 'Amend observations'),
            (
                gen_random_uuid(),
                'clinical.observation.entered_in_error',
                'Mark observations entered in error'
            );
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r
        JOIN permissions p ON (
            (r.code IN ('PLATFORM_ADMIN','CLINICIAN') AND p.code LIKE 'clinical.observation.%')
            OR (r.code IN ('ORG_ADMIN','AUDITOR') AND p.code = 'clinical.observation.read')
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
            SELECT id FROM permissions WHERE code LIKE 'clinical.observation.%'
        );
        """
    )
    op.execute("DELETE FROM permissions WHERE code LIKE 'clinical.observation.%';")
    op.execute("DROP TRIGGER IF EXISTS trg_observations_history_immutable ON observations;")
    op.execute("DROP FUNCTION IF EXISTS prevent_observation_history_mutation();")
    op.execute("ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS clinical_provenance_subject;")
    op.execute(
        "ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS "
        "ck_clinical_provenances_clinical_provenance_subject;"
    )
    op.execute(
        """
        ALTER TABLE clinical_provenances
        ADD CONSTRAINT clinical_provenance_subject CHECK (
            subject_type IN ('ENCOUNTER','CLINICAL_NOTE','CONDITION')
        );
        """
    )
    op.drop_index("ix_observations_recorded_at", table_name="observations")
    op.drop_index("ix_observations_organization_id", table_name="observations")
    op.drop_index("ix_observations_encounter_id", table_name="observations")
    op.drop_index("ix_observations_patient_identity_id", table_name="observations")
    op.drop_table("observations")
