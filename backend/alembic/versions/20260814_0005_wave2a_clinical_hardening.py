"""Wave 2A hardening: immutable clinical history.

Revision ID: 20260814_0005
Revises: 20260814_0004
Create Date: 2026-08-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260814_0005"
down_revision: str | None = "20260814_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_final_clinical_note_content_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'clinical notes cannot be deleted';
            END IF;
            IF NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id
               OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id THEN
                RAISE EXCEPTION 'clinical note patient and encounter are immutable';
            END IF;
            IF OLD.record_status = 'ENTERED_IN_ERROR' THEN
                RAISE EXCEPTION 'entered-in-error clinical note is immutable';
            END IF;
            IF OLD.record_status = 'FINAL' AND (
                NEW.body_text IS DISTINCT FROM OLD.body_text
                OR NEW.note_type IS DISTINCT FROM OLD.note_type
                OR NEW.author_id IS DISTINCT FROM OLD.author_id
                OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
                OR (
                    NEW.record_status IS DISTINCT FROM OLD.record_status
                    AND NEW.record_status IS DISTINCT FROM 'ENTERED_IN_ERROR'
                )
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
        CREATE OR REPLACE FUNCTION prevent_clinical_encounter_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'encounters cannot be deleted';
            END IF;
            IF NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id THEN
                RAISE EXCEPTION 'encounter patient identity is immutable';
            END IF;
            IF OLD.status = 'ENTERED_IN_ERROR'
               AND NEW.status IS DISTINCT FROM OLD.status THEN
                RAISE EXCEPTION 'entered-in-error encounter status is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_clinical_encounters_history_immutable ON encounters;"
    )
    op.execute(
        """
        CREATE TRIGGER trg_clinical_encounters_history_immutable
        BEFORE UPDATE OR DELETE ON encounters
        FOR EACH ROW
        EXECUTE FUNCTION prevent_clinical_encounter_history_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_clinical_encounters_history_immutable ON encounters;")
    op.execute("DROP FUNCTION IF EXISTS prevent_clinical_encounter_history_mutation();")
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
