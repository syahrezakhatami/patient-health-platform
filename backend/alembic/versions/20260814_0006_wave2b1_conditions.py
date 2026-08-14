"""Wave 2B.1 conditions: problem list and encounter diagnosis.

Revision ID: 20260814_0006
Revises: 20260814_0005
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0006"
down_revision: str | None = "20260814_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conditions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("code_system", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("code_display", sa.String(length=255), nullable=True),
        sa.Column("clinical_status", sa.String(length=32), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("onset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abatement_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "category IN ('PROBLEM_LIST_ITEM','ENCOUNTER_DIAGNOSIS')",
            name="condition_category",
        ),
        sa.CheckConstraint(
            "clinical_status IN ('ACTIVE','RECURRENCE','RELAPSE','INACTIVE','REMISSION','RESOLVED')",
            name="condition_clinical_status",
        ),
        sa.CheckConstraint(
            "verification_status IN ("
            "'UNCONFIRMED','PROVISIONAL','DIFFERENTIAL','CONFIRMED','REFUTED','ENTERED_IN_ERROR'"
            ")",
            name="condition_verification_status",
        ),
        sa.CheckConstraint(
            "category <> 'ENCOUNTER_DIAGNOSIS' OR encounter_id IS NOT NULL",
            name="condition_encounter_diagnosis_requires_encounter",
        ),
        sa.CheckConstraint(
            "abatement_at IS NULL OR onset_at IS NULL OR abatement_at >= onset_at",
            name="condition_period",
        ),
        sa.CheckConstraint("char_length(code_system) > 0", name="condition_code_system_required"),
        sa.CheckConstraint("char_length(code) > 0", name="condition_code_required"),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_conditions_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_conditions_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_conditions_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_conditions_facility_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conditions"),
    )
    op.create_index("ix_conditions_patient_identity_id", "conditions", ["patient_identity_id"])
    op.create_index("ix_conditions_encounter_id", "conditions", ["encounter_id"])
    op.create_index("ix_conditions_organization_id", "conditions", ["organization_id"])
    op.create_index("ix_conditions_recorded_at", "conditions", ["recorded_at"])

    op.execute("ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS clinical_provenance_subject;")
    op.execute(
        "ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS ck_clinical_provenances_clinical_provenance_subject;"
    )
    op.execute(
        """
        ALTER TABLE clinical_provenances
        ADD CONSTRAINT clinical_provenance_subject CHECK (
            subject_type IN ('ENCOUNTER','CLINICAL_NOTE','CONDITION')
        );
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_condition_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'conditions cannot be deleted';
            END IF;
            IF NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id
               OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.category IS DISTINCT FROM OLD.category
               OR NEW.code_system IS DISTINCT FROM OLD.code_system
               OR NEW.code IS DISTINCT FROM OLD.code
               OR NEW.code_display IS DISTINCT FROM OLD.code_display
               OR NEW.recorder_id IS DISTINCT FROM OLD.recorder_id THEN
                RAISE EXCEPTION 'condition identity, encounter, category, and code are immutable';
            END IF;
            IF OLD.verification_status = 'ENTERED_IN_ERROR' THEN
                RAISE EXCEPTION 'entered-in-error condition is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_conditions_history_immutable
        BEFORE UPDATE OR DELETE ON conditions
        FOR EACH ROW
        EXECUTE FUNCTION prevent_condition_history_mutation();
        """
    )

    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'clinical.condition.create', 'Create conditions'),
            (gen_random_uuid(), 'clinical.condition.read', 'Read conditions'),
            (gen_random_uuid(), 'clinical.condition.update', 'Update condition status'),
            (
                gen_random_uuid(),
                'clinical.condition.entered_in_error',
                'Mark conditions entered in error'
            );
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r
        JOIN permissions p ON (
            (r.code IN ('PLATFORM_ADMIN','CLINICIAN') AND p.code LIKE 'clinical.condition.%')
            OR (r.code IN ('ORG_ADMIN','AUDITOR') AND p.code = 'clinical.condition.read')
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
            SELECT id FROM permissions WHERE code LIKE 'clinical.condition.%'
        );
        """
    )
    op.execute("DELETE FROM permissions WHERE code LIKE 'clinical.condition.%';")
    op.execute("DROP TRIGGER IF EXISTS trg_conditions_history_immutable ON conditions;")
    op.execute("DROP FUNCTION IF EXISTS prevent_condition_history_mutation();")
    op.execute("ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS clinical_provenance_subject;")
    op.execute(
        "ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS ck_clinical_provenances_clinical_provenance_subject;"
    )
    op.execute(
        """
        ALTER TABLE clinical_provenances
        ADD CONSTRAINT clinical_provenance_subject CHECK (
            subject_type IN ('ENCOUNTER','CLINICAL_NOTE')
        );
        """
    )
    op.drop_index("ix_conditions_recorded_at", table_name="conditions")
    op.drop_index("ix_conditions_organization_id", table_name="conditions")
    op.drop_index("ix_conditions_encounter_id", table_name="conditions")
    op.drop_index("ix_conditions_patient_identity_id", table_name="conditions")
    op.drop_table("conditions")
