"""Wave 2A clinical foundation: encounters and clinical notes.

Revision ID: 20260814_0004
Revises: 20260813_0003
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0004"
down_revision: str | None = "20260813_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "encounters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("encounter_class", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("display_label", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason_system", sa.String(length=128), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("reason_display", sa.String(length=255), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "encounter_class IN ('EMER','IMP','AMB','VR','HH')",
            name="encounter_class",
        ),
        sa.CheckConstraint(
            "status IN ('PLANNED','IN_PROGRESS','FINISHED','CANCELLED','ENTERED_IN_ERROR')",
            name="encounter_status",
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="encounter_period",
        ),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_encounters_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_encounters_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_encounters_facility_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_encounters"),
    )
    op.create_index("ix_encounters_patient_identity_id", "encounters", ["patient_identity_id"])
    op.create_index("ix_encounters_organization_id", "encounters", ["organization_id"])
    op.create_index("ix_encounters_started_at", "encounters", ["started_at"])
    op.create_index("ix_encounters_status", "encounters", ["status"])

    op.create_table(
        "encounter_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participation_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "participation_type IN ('ATTENDING','ADMITTING','CONSULTANT','OTHER')",
            name="participation_type",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_encounter_participants_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_encounter_participants"),
    )
    op.create_index(
        "ix_encounter_participants_encounter_id",
        "encounter_participants",
        ["encounter_id"],
    )

    op.create_table(
        "clinical_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note_type", sa.String(length=32), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("record_status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("authored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "note_type IN ('PROGRESS','ADMISSION','ED','DISCHARGE','OTHER')",
            name="clinical_note_type",
        ),
        sa.CheckConstraint(
            "record_status IN ('DRAFT','FINAL','ENTERED_IN_ERROR')",
            name="clinical_note_status",
        ),
        sa.CheckConstraint("version >= 1", name="clinical_note_version"),
        sa.CheckConstraint("char_length(body_text) > 0", name="clinical_note_body_required"),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_clinical_notes_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_clinical_notes_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_clinical_notes_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_clinical_notes_facility_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["clinical_notes.id"],
            name="fk_clinical_notes_supersedes_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clinical_notes"),
    )
    op.create_index("ix_clinical_notes_patient_identity_id", "clinical_notes", ["patient_identity_id"])
    op.create_index("ix_clinical_notes_encounter_id", "clinical_notes", ["encounter_id"])
    op.create_index("ix_clinical_notes_authored_at", "clinical_notes", ["authored_at"])

    op.create_table(
        "clinical_provenances",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verification_method", sa.String(length=64), nullable=True),
        sa.Column("authorship_kind", sa.String(length=32), nullable=False),
        sa.Column("information_source", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "subject_type IN ('ENCOUNTER','CLINICAL_NOTE')",
            name="clinical_provenance_subject",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clinical_provenances"),
    )
    op.create_index(
        "ix_clinical_provenances_subject",
        "clinical_provenances",
        ["subject_type", "subject_id"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_final_clinical_note_content_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'clinical notes cannot be deleted';
            END IF;
            IF OLD.record_status IN ('FINAL', 'ENTERED_IN_ERROR') AND (
                NEW.body_text IS DISTINCT FROM OLD.body_text
                OR NEW.note_type IS DISTINCT FROM OLD.note_type
                OR NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id
                OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
            ) THEN
                RAISE EXCEPTION 'final clinical note content is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_clinical_notes_final_immutable
        BEFORE UPDATE OR DELETE ON clinical_notes
        FOR EACH ROW
        EXECUTE FUNCTION prevent_final_clinical_note_content_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_clinical_provenances_immutable
        BEFORE UPDATE OR DELETE ON clinical_provenances
        FOR EACH ROW
        EXECUTE FUNCTION prevent_identity_history_mutation();
        """
    )

    op.execute("ALTER TABLE identity_match_probes DROP CONSTRAINT IF EXISTS match_probe_purpose;")
    op.execute(
        """
        ALTER TABLE identity_match_probes
        ADD CONSTRAINT match_probe_purpose CHECK (
            purpose IN (
                'REGISTRATION','IDENTITY_RESOLUTION','EMERGENCY','CARE_COORDINATION',
                'ADMINISTRATION','PATIENT_ACCESS','AUDIT','SYSTEM_OPERATION','TREATMENT'
            )
        );
        """
    )

    op.execute(
        """
        INSERT INTO roles (id, code, name)
        VALUES (gen_random_uuid(), 'CLINICIAN', 'Clinician')
        ON CONFLICT (code) DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'clinical.encounter.create', 'Create encounters'),
            (gen_random_uuid(), 'clinical.encounter.read', 'Read encounters'),
            (gen_random_uuid(), 'clinical.encounter.update_status', 'Change encounter status'),
            (gen_random_uuid(), 'clinical.note.create', 'Create clinical notes'),
            (gen_random_uuid(), 'clinical.note.read', 'Read clinical notes'),
            (gen_random_uuid(), 'clinical.note.update_draft', 'Update draft clinical notes'),
            (gen_random_uuid(), 'clinical.note.finalize', 'Finalize or mark clinical notes entered in error');
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r
        JOIN permissions p ON (
            (r.code = 'PLATFORM_ADMIN' AND p.code LIKE 'clinical.%')
            OR (r.code = 'CLINICIAN' AND (
                p.code LIKE 'clinical.%'
                OR p.code IN (
                    'iam.user.read',
                    'org.organization.read',
                    'org.facility.read',
                    'mpi.identity.read'
                )
            ))
            OR (r.code = 'REGISTRAR' AND p.code IN (
                'clinical.encounter.create','clinical.encounter.read'
            ))
            OR (r.code = 'ORG_ADMIN' AND p.code IN (
                'clinical.encounter.read','clinical.note.read'
            ))
            OR (r.code = 'AUDITOR' AND p.code IN (
                'clinical.encounter.read','clinical.note.read'
            ))
        )
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permissions existing
            WHERE existing.role_id = r.id AND existing.permission_id = p.id
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_clinical_provenances_immutable ON clinical_provenances;")
    op.execute("DROP TRIGGER IF EXISTS trg_clinical_notes_final_immutable ON clinical_notes;")
    op.execute("DROP FUNCTION IF EXISTS prevent_final_clinical_note_content_mutation();")
    op.drop_table("clinical_provenances")
    op.drop_table("clinical_notes")
    op.drop_table("encounter_participants")
    op.drop_index("ix_encounters_status", table_name="encounters")
    op.drop_index("ix_encounters_started_at", table_name="encounters")
    op.drop_index("ix_encounters_organization_id", table_name="encounters")
    op.drop_index("ix_encounters_patient_identity_id", table_name="encounters")
    op.drop_table("encounters")
    op.execute("ALTER TABLE identity_match_probes DROP CONSTRAINT IF EXISTS match_probe_purpose;")
    op.execute(
        """
        ALTER TABLE identity_match_probes
        ADD CONSTRAINT match_probe_purpose CHECK (
            purpose IN (
                'REGISTRATION','IDENTITY_RESOLUTION','EMERGENCY','CARE_COORDINATION',
                'ADMINISTRATION','PATIENT_ACCESS','AUDIT','SYSTEM_OPERATION'
            )
        );
        """
    )
