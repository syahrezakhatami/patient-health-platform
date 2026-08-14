"""Wave 2B.1 Condition integrity: provenance FK and historical-fact immutability.

Revision ID: 20260814_0007
Revises: 20260814_0006
Create Date: 2026-08-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260814_0007"
down_revision: str | None = "20260814_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM conditions c
                WHERE c.provenance_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM clinical_provenances p WHERE p.id = c.provenance_id
                  )
            ) THEN
                RAISE EXCEPTION 'conditions.provenance_id has orphan references';
            END IF;
        END
        $$;
        """
    )
    op.create_foreign_key(
        "fk_conditions_provenance_id",
        "conditions",
        "clinical_provenances",
        ["provenance_id"],
        ["id"],
        ondelete="RESTRICT",
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
               OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
               OR NEW.category IS DISTINCT FROM OLD.category
               OR NEW.code_system IS DISTINCT FROM OLD.code_system
               OR NEW.code IS DISTINCT FROM OLD.code
               OR NEW.code_display IS DISTINCT FROM OLD.code_display
               OR NEW.onset_at IS DISTINCT FROM OLD.onset_at
               OR NEW.abatement_at IS DISTINCT FROM OLD.abatement_at
               OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
               OR NEW.recorder_id IS DISTINCT FROM OLD.recorder_id
               OR NEW.provenance_id IS DISTINCT FROM OLD.provenance_id THEN
                RAISE EXCEPTION 'condition historical facts are immutable';
            END IF;
            IF OLD.verification_status = 'ENTERED_IN_ERROR' THEN
                RAISE EXCEPTION 'entered-in-error condition is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
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
    op.drop_constraint("fk_conditions_provenance_id", "conditions", type_="foreignkey")
