"""Wave 2B.3c native consents.

Revision ID: 20260814_0012
Revises: 20260814_0011
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0012"
down_revision: str | None = "20260814_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("code_system", sa.String(length=128), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("code_display", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "category IN ('TREATMENT','DISCLOSURE','PRIVACY','OTHER')",
            name="consent_category",
        ),
        sa.CheckConstraint(
            "scope IN ('ORGANIZATION','ENCOUNTER')",
            name="consent_scope",
        ),
        sa.CheckConstraint(
            "decision IN ('PERMIT','DENY')",
            name="consent_decision",
        ),
        sa.CheckConstraint(
            "source IN ('PATIENT','REPRESENTATIVE','CLINICIAN_DOCUMENTED')",
            name="consent_source",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','AMENDED','REVOKED','ENTERED_IN_ERROR')",
            name="consent_status",
        ),
        sa.CheckConstraint("version >= 1", name="consent_version_positive"),
        sa.CheckConstraint(
            "period_end IS NULL OR period_start IS NULL OR period_end >= period_start",
            name="consent_period_order",
        ),
        sa.CheckConstraint(
            """
            (status = 'REVOKED' AND revoked_at IS NOT NULL)
            OR (status <> 'REVOKED' AND revoked_at IS NULL)
            """,
            name="consent_revoked_at_matches_status",
        ),
        sa.CheckConstraint(
            """
            (code_system IS NULL AND code IS NULL)
            OR (
                char_length(code_system) > 0
                AND char_length(code) > 0
            )
            """,
            name="consent_code_shape",
        ),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_consents_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_consents_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_consents_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_consents_facility_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["clinical_provenances.id"],
            name="fk_consents_provenance_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_consents"),
    )
    op.create_index("ix_consents_patient_identity_id", "consents", ["patient_identity_id"])
    op.create_index("ix_consents_encounter_id", "consents", ["encounter_id"])
    op.create_index("ix_consents_organization_id", "consents", ["organization_id"])
    op.create_index("ix_consents_facility_id", "consents", ["facility_id"])
    op.create_index("ix_consents_status", "consents", ["status"])
    op.create_index("ix_consents_recorded_at", "consents", ["recorded_at"])
    op.create_index(
        "ix_consents_patient_org_status",
        "consents",
        ["patient_identity_id", "organization_id", "status"],
    )
    op.create_index("ix_consents_period_end", "consents", ["period_end"])

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

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_consent_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'consents cannot be deleted';
            END IF;
            IF NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id
               OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
               OR NEW.category IS DISTINCT FROM OLD.category
               OR NEW.scope IS DISTINCT FROM OLD.scope
               OR NEW.decision IS DISTINCT FROM OLD.decision
               OR NEW.code_system IS DISTINCT FROM OLD.code_system
               OR NEW.code IS DISTINCT FROM OLD.code
               OR NEW.code_display IS DISTINCT FROM OLD.code_display
               OR NEW.source IS DISTINCT FROM OLD.source
               OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
               OR NEW.recorder_id IS DISTINCT FROM OLD.recorder_id
               OR NEW.provenance_id IS DISTINCT FROM OLD.provenance_id THEN
                RAISE EXCEPTION 'consent historical facts are immutable';
            END IF;
            IF OLD.status IN ('REVOKED', 'ENTERED_IN_ERROR') THEN
                RAISE EXCEPTION 'terminal consent is immutable';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status
               AND NOT (
                    (OLD.status = 'ACTIVE' AND NEW.status IN (
                        'AMENDED','REVOKED','ENTERED_IN_ERROR'
                    ))
                    OR (OLD.status = 'AMENDED' AND NEW.status IN (
                        'AMENDED','REVOKED','ENTERED_IN_ERROR'
                    ))
               ) THEN
                RAISE EXCEPTION 'invalid consent status transition';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_consents_history_immutable
        BEFORE UPDATE OR DELETE ON consents
        FOR EACH ROW
        EXECUTE FUNCTION prevent_consent_history_mutation();
        """
    )

    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'clinical.consent.create', 'Create consents'),
            (gen_random_uuid(), 'clinical.consent.read', 'Read consents'),
            (gen_random_uuid(), 'clinical.consent.update', 'Amend consents'),
            (gen_random_uuid(), 'clinical.consent.revoke', 'Revoke consents'),
            (
                gen_random_uuid(),
                'clinical.consent.entered_in_error',
                'Mark consents entered in error'
            );
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r
        JOIN permissions p ON (
            (r.code IN ('PLATFORM_ADMIN','CLINICIAN') AND p.code LIKE 'clinical.consent.%')
            OR (r.code IN ('ORG_ADMIN','AUDITOR') AND p.code = 'clinical.consent.read')
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
            SELECT id FROM permissions WHERE code LIKE 'clinical.consent.%'
        );
        """
    )
    op.execute("DELETE FROM permissions WHERE code LIKE 'clinical.consent.%';")
    op.execute("DROP TRIGGER IF EXISTS trg_consents_history_immutable ON consents;")
    op.execute("DROP FUNCTION IF EXISTS prevent_consent_history_mutation();")
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
    op.drop_index("ix_consents_period_end", table_name="consents")
    op.drop_index("ix_consents_patient_org_status", table_name="consents")
    op.drop_index("ix_consents_recorded_at", table_name="consents")
    op.drop_index("ix_consents_status", table_name="consents")
    op.drop_index("ix_consents_facility_id", table_name="consents")
    op.drop_index("ix_consents_organization_id", table_name="consents")
    op.drop_index("ix_consents_encounter_id", table_name="consents")
    op.drop_index("ix_consents_patient_identity_id", table_name="consents")
    op.drop_table("consents")
