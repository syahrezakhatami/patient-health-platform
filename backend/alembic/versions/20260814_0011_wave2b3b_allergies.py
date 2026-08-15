"""Wave 2B.3b native allergies.

Revision ID: 20260814_0011
Revises: 20260814_0010
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0011"
down_revision: str | None = "20260814_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "allergies",
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
        sa.Column("clinical_status", sa.String(length=32), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("criticality", sa.String(length=32), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("reaction_code_system", sa.String(length=128), nullable=True),
        sa.Column("reaction_code", sa.String(length=64), nullable=True),
        sa.Column("reaction_display", sa.String(length=255), nullable=True),
        sa.Column("onset_at", sa.DateTime(timezone=True), nullable=True),
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
            "category IN ('DRUG','FOOD','ENVIRONMENT','OTHER')",
            name="allergy_category",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','AMENDED','ENTERED_IN_ERROR')",
            name="allergy_status",
        ),
        sa.CheckConstraint(
            "clinical_status IN ('ACTIVE','INACTIVE')",
            name="allergy_clinical_status",
        ),
        sa.CheckConstraint(
            "verification_status IN ('UNCONFIRMED','CONFIRMED','REFUTED')",
            name="allergy_verification_status",
        ),
        sa.CheckConstraint(
            "criticality IS NULL OR criticality IN ('LOW','HIGH','UNABLE_TO_ASSESS')",
            name="allergy_criticality",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('MILD','MODERATE','SEVERE')",
            name="allergy_severity",
        ),
        sa.CheckConstraint("char_length(code_system) > 0", name="allergy_code_system_required"),
        sa.CheckConstraint("char_length(code) > 0", name="allergy_code_required"),
        sa.CheckConstraint("version >= 1", name="allergy_version_positive"),
        sa.CheckConstraint(
            """
            (reaction_code_system IS NULL AND reaction_code IS NULL)
            OR (
                char_length(reaction_code_system) > 0
                AND char_length(reaction_code) > 0
            )
            """,
            name="allergy_reaction_shape",
        ),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_allergies_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_allergies_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_allergies_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_allergies_facility_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["clinical_provenances.id"],
            name="fk_allergies_provenance_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_allergies"),
    )
    op.create_index("ix_allergies_patient_identity_id", "allergies", ["patient_identity_id"])
    op.create_index("ix_allergies_encounter_id", "allergies", ["encounter_id"])
    op.create_index("ix_allergies_organization_id", "allergies", ["organization_id"])
    op.create_index("ix_allergies_recorded_at", "allergies", ["recorded_at"])

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
                'MEDICATION','ALLERGY'
            )
        );
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_allergy_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'allergies cannot be deleted';
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
                RAISE EXCEPTION 'allergy historical facts are immutable';
            END IF;
            IF OLD.status = 'ENTERED_IN_ERROR' THEN
                RAISE EXCEPTION 'entered-in-error allergy is immutable';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status
               AND NOT (
                    (OLD.status = 'ACTIVE' AND NEW.status IN ('AMENDED','ENTERED_IN_ERROR'))
                    OR (OLD.status = 'AMENDED' AND NEW.status = 'ENTERED_IN_ERROR')
               ) THEN
                RAISE EXCEPTION 'invalid allergy status transition';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_allergies_history_immutable
        BEFORE UPDATE OR DELETE ON allergies
        FOR EACH ROW
        EXECUTE FUNCTION prevent_allergy_history_mutation();
        """
    )

    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'clinical.allergy.create', 'Create allergies'),
            (gen_random_uuid(), 'clinical.allergy.read', 'Read allergies'),
            (gen_random_uuid(), 'clinical.allergy.update', 'Amend allergies'),
            (
                gen_random_uuid(),
                'clinical.allergy.entered_in_error',
                'Mark allergies entered in error'
            );
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r
        JOIN permissions p ON (
            (r.code IN ('PLATFORM_ADMIN','CLINICIAN') AND p.code LIKE 'clinical.allergy.%')
            OR (r.code IN ('ORG_ADMIN','AUDITOR') AND p.code = 'clinical.allergy.read')
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
            SELECT id FROM permissions WHERE code LIKE 'clinical.allergy.%'
        );
        """
    )
    op.execute("DELETE FROM permissions WHERE code LIKE 'clinical.allergy.%';")
    op.execute("DROP TRIGGER IF EXISTS trg_allergies_history_immutable ON allergies;")
    op.execute("DROP FUNCTION IF EXISTS prevent_allergy_history_mutation();")
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
    op.drop_index("ix_allergies_recorded_at", table_name="allergies")
    op.drop_index("ix_allergies_organization_id", table_name="allergies")
    op.drop_index("ix_allergies_encounter_id", table_name="allergies")
    op.drop_index("ix_allergies_patient_identity_id", table_name="allergies")
    op.drop_table("allergies")
