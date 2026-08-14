"""Wave 2B.3a native medications.

Revision ID: 20260814_0010
Revises: 20260814_0009
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0010"
down_revision: str | None = "20260814_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "medications",
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
        sa.Column("dose_numeric", sa.Numeric(14, 4), nullable=True),
        sa.Column("dose_unit", sa.String(length=32), nullable=True),
        sa.Column("route", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
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
            "category IN ('PRESCRIBED','REPORTED')",
            name="medication_category",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','STOPPED','ENTERED_IN_ERROR')",
            name="medication_status",
        ),
        sa.CheckConstraint(
            "route IS NULL OR route IN ('ORAL','IV','IM','SC','TOPICAL','INHALED','OTHER')",
            name="medication_route",
        ),
        sa.CheckConstraint("char_length(code_system) > 0", name="medication_code_system_required"),
        sa.CheckConstraint("char_length(code) > 0", name="medication_code_required"),
        sa.CheckConstraint("version >= 1", name="medication_version_positive"),
        sa.CheckConstraint(
            """
            (dose_numeric IS NULL AND dose_unit IS NULL)
            OR (dose_numeric IS NOT NULL AND char_length(dose_unit) > 0)
            """,
            name="medication_dose_shape",
        ),
        sa.CheckConstraint(
            """
            (status = 'ACTIVE' AND stopped_at IS NULL)
            OR (status = 'STOPPED' AND stopped_at IS NOT NULL)
            OR (status = 'ENTERED_IN_ERROR')
            """,
            name="medication_stopped_at_shape",
        ),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_medications_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_medications_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_medications_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_medications_facility_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["clinical_provenances.id"],
            name="fk_medications_provenance_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_medications"),
    )
    op.create_index("ix_medications_patient_identity_id", "medications", ["patient_identity_id"])
    op.create_index("ix_medications_encounter_id", "medications", ["encounter_id"])
    op.create_index("ix_medications_organization_id", "medications", ["organization_id"])
    op.create_index("ix_medications_recorded_at", "medications", ["recorded_at"])

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
                'MEDICATION'
            )
        );
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_medication_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'medications cannot be deleted';
            END IF;
            IF NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id
               OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
               OR NEW.category IS DISTINCT FROM OLD.category
               OR NEW.code_system IS DISTINCT FROM OLD.code_system
               OR NEW.code IS DISTINCT FROM OLD.code
               OR NEW.code_display IS DISTINCT FROM OLD.code_display
               OR NEW.dose_numeric IS DISTINCT FROM OLD.dose_numeric
               OR NEW.dose_unit IS DISTINCT FROM OLD.dose_unit
               OR NEW.route IS DISTINCT FROM OLD.route
               OR NEW.started_at IS DISTINCT FROM OLD.started_at
               OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
               OR NEW.recorder_id IS DISTINCT FROM OLD.recorder_id
               OR NEW.provenance_id IS DISTINCT FROM OLD.provenance_id THEN
                RAISE EXCEPTION 'medication historical facts are immutable';
            END IF;
            IF OLD.stopped_at IS NOT NULL
               AND NEW.stopped_at IS DISTINCT FROM OLD.stopped_at THEN
                RAISE EXCEPTION 'medication historical facts are immutable';
            END IF;
            IF OLD.status = 'ENTERED_IN_ERROR' THEN
                RAISE EXCEPTION 'entered-in-error medication is immutable';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status
               AND NOT (
                    (OLD.status = 'ACTIVE' AND NEW.status IN ('STOPPED','ENTERED_IN_ERROR'))
                    OR (OLD.status = 'STOPPED' AND NEW.status = 'ENTERED_IN_ERROR')
               ) THEN
                RAISE EXCEPTION 'invalid medication status transition';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_medications_history_immutable
        BEFORE UPDATE OR DELETE ON medications
        FOR EACH ROW
        EXECUTE FUNCTION prevent_medication_history_mutation();
        """
    )

    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'clinical.medication.create', 'Create medications'),
            (gen_random_uuid(), 'clinical.medication.read', 'Read medications'),
            (gen_random_uuid(), 'clinical.medication.update', 'Stop medications'),
            (
                gen_random_uuid(),
                'clinical.medication.entered_in_error',
                'Mark medications entered in error'
            );
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r
        JOIN permissions p ON (
            (r.code IN ('PLATFORM_ADMIN','CLINICIAN') AND p.code LIKE 'clinical.medication.%')
            OR (r.code IN ('ORG_ADMIN','AUDITOR') AND p.code = 'clinical.medication.read')
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
            SELECT id FROM permissions WHERE code LIKE 'clinical.medication.%'
        );
        """
    )
    op.execute("DELETE FROM permissions WHERE code LIKE 'clinical.medication.%';")
    op.execute("DROP TRIGGER IF EXISTS trg_medications_history_immutable ON medications;")
    op.execute("DROP FUNCTION IF EXISTS prevent_medication_history_mutation();")
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
                'LABORATORY_ORDER','LABORATORY_SPECIMEN','LABORATORY_RESULT'
            )
        );
        """
    )
    op.drop_index("ix_medications_recorded_at", table_name="medications")
    op.drop_index("ix_medications_organization_id", table_name="medications")
    op.drop_index("ix_medications_encounter_id", table_name="medications")
    op.drop_index("ix_medications_patient_identity_id", table_name="medications")
    op.drop_table("medications")
