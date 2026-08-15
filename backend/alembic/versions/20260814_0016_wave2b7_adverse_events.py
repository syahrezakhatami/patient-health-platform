"""Wave 2B.7 native adverse events.

Revision ID: 20260814_0016
Revises: 20260814_0015
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0016"
down_revision: str | None = "20260814_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "adverse_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("code_system", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("code_display", sa.String(length=255), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("medication_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("medical_device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("procedure_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurrence_at", sa.DateTime(timezone=True), nullable=True),
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
            "category IN ('DOCUMENTED','REPORTED')",
            name="adverse_event_category",
        ),
        sa.CheckConstraint(
            "severity IN ('MILD','MODERATE','SEVERE')",
            name="adverse_event_severity",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','AMENDED','ENTERED_IN_ERROR')",
            name="adverse_event_status",
        ),
        sa.CheckConstraint(
            "("
            "CASE WHEN medication_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN medical_device_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN procedure_id IS NULL THEN 0 ELSE 1 END"
            ") <= 1",
            name="adverse_event_related_fact_at_most_one",
        ),
        sa.CheckConstraint(
            "char_length(code_system) > 0", name="adverse_event_code_system_required"
        ),
        sa.CheckConstraint("char_length(code) > 0", name="adverse_event_code_required"),
        sa.CheckConstraint("version >= 1", name="adverse_event_version_positive"),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_adverse_events_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_adverse_events_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_adverse_events_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_adverse_events_facility_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["medication_id"],
            ["medications.id"],
            name="fk_adverse_events_medication_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["medical_device_id"],
            ["medical_devices.id"],
            name="fk_adverse_events_medical_device_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["procedure_id"],
            ["procedures.id"],
            name="fk_adverse_events_procedure_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["clinical_provenances.id"],
            name="fk_adverse_events_provenance_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_adverse_events"),
    )
    op.create_index(
        "ix_adverse_events_patient_identity_id", "adverse_events", ["patient_identity_id"]
    )
    op.create_index("ix_adverse_events_encounter_id", "adverse_events", ["encounter_id"])
    op.create_index("ix_adverse_events_organization_id", "adverse_events", ["organization_id"])
    op.create_index("ix_adverse_events_recorded_at", "adverse_events", ["recorded_at"])

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
                'MEDICATION','ALLERGY','CONSENT','IMMUNIZATION','PROCEDURE',
                'MEDICAL_DEVICE','ADVERSE_EVENT'
            )
        );
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_adverse_event_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'adverse_events cannot be deleted';
            END IF;
            IF NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id
               OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
               OR NEW.category IS DISTINCT FROM OLD.category
               OR NEW.code_system IS DISTINCT FROM OLD.code_system
               OR NEW.code IS DISTINCT FROM OLD.code
               OR NEW.code_display IS DISTINCT FROM OLD.code_display
               OR NEW.medication_id IS DISTINCT FROM OLD.medication_id
               OR NEW.medical_device_id IS DISTINCT FROM OLD.medical_device_id
               OR NEW.procedure_id IS DISTINCT FROM OLD.procedure_id
               OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
               OR NEW.recorder_id IS DISTINCT FROM OLD.recorder_id
               OR NEW.provenance_id IS DISTINCT FROM OLD.provenance_id THEN
                RAISE EXCEPTION 'adverse event historical facts are immutable';
            END IF;
            IF OLD.status = 'ENTERED_IN_ERROR' THEN
                RAISE EXCEPTION 'entered-in-error adverse event is immutable';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status
               AND NOT (
                    (OLD.status = 'ACTIVE' AND NEW.status IN ('AMENDED','ENTERED_IN_ERROR'))
                    OR (OLD.status = 'AMENDED' AND NEW.status = 'ENTERED_IN_ERROR')
               ) THEN
                RAISE EXCEPTION 'invalid adverse event status transition';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_adverse_events_history_immutable
        BEFORE UPDATE OR DELETE ON adverse_events
        FOR EACH ROW
        EXECUTE FUNCTION prevent_adverse_event_history_mutation();
        """
    )

    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'clinical.adverse_event.create', 'Create adverse events'),
            (gen_random_uuid(), 'clinical.adverse_event.read', 'Read adverse events'),
            (gen_random_uuid(), 'clinical.adverse_event.update', 'Amend adverse events'),
            (
                gen_random_uuid(),
                'clinical.adverse_event.entered_in_error',
                'Mark adverse events entered in error'
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
                AND p.code LIKE 'clinical.adverse_event.%'
            )
            OR (
                r.code IN ('ORG_ADMIN','AUDITOR')
                AND p.code = 'clinical.adverse_event.read'
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
            SELECT id FROM permissions WHERE code LIKE 'clinical.adverse_event.%'
        );
        """
    )
    op.execute("DELETE FROM permissions WHERE code LIKE 'clinical.adverse_event.%';")
    op.execute("DROP TRIGGER IF EXISTS trg_adverse_events_history_immutable ON adverse_events;")
    op.execute("DROP FUNCTION IF EXISTS prevent_adverse_event_history_mutation();")
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
                'MEDICATION','ALLERGY','CONSENT','IMMUNIZATION','PROCEDURE',
                'MEDICAL_DEVICE'
            )
        );
        """
    )
    op.drop_index("ix_adverse_events_recorded_at", table_name="adverse_events")
    op.drop_index("ix_adverse_events_organization_id", table_name="adverse_events")
    op.drop_index("ix_adverse_events_encounter_id", table_name="adverse_events")
    op.drop_index("ix_adverse_events_patient_identity_id", table_name="adverse_events")
    op.drop_table("adverse_events")
