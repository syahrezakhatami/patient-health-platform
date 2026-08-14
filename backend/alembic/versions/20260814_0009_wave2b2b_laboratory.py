"""Wave 2B.2b native laboratory orders, specimens, and results.

Revision ID: 20260814_0009
Revises: 20260814_0008
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0009"
down_revision: str | None = "20260814_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALUE_SHAPE = """
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
"""


def upgrade() -> None:
    op.create_table(
        "laboratory_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code_system", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("code_display", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('REGISTERED','IN_PROGRESS','CANCELLED','ENTERED_IN_ERROR')",
            name="lab_order_status",
        ),
        sa.CheckConstraint("char_length(code_system) > 0", name="lab_order_code_system_required"),
        sa.CheckConstraint("char_length(code) > 0", name="lab_order_code_required"),
        sa.CheckConstraint("version >= 1", name="lab_order_version_positive"),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_laboratory_orders_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_laboratory_orders_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_laboratory_orders_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_laboratory_orders_facility_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["clinical_provenances.id"],
            name="fk_laboratory_orders_provenance_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_laboratory_orders"),
    )
    op.create_index(
        "ix_laboratory_orders_patient_identity_id", "laboratory_orders", ["patient_identity_id"]
    )
    op.create_index("ix_laboratory_orders_encounter_id", "laboratory_orders", ["encounter_id"])
    op.create_index("ix_laboratory_orders_organization_id", "laboratory_orders", ["organization_id"])

    op.create_table(
        "laboratory_specimens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("laboratory_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("specimen_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "specimen_type IN ('BLOOD','URINE','SWAB','OTHER')",
            name="lab_specimen_type",
        ),
        sa.CheckConstraint(
            "status IN ('COLLECTED','REJECTED','ENTERED_IN_ERROR')",
            name="lab_specimen_status",
        ),
        sa.ForeignKeyConstraint(
            ["laboratory_order_id"],
            ["laboratory_orders.id"],
            name="fk_laboratory_specimens_order_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_laboratory_specimens_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_laboratory_specimens_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_laboratory_specimens_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_laboratory_specimens_facility_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["clinical_provenances.id"],
            name="fk_laboratory_specimens_provenance_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_laboratory_specimens"),
    )
    op.create_index(
        "ix_laboratory_specimens_order_id", "laboratory_specimens", ["laboratory_order_id"]
    )
    op.create_index(
        "ix_laboratory_specimens_patient_identity_id",
        "laboratory_specimens",
        ["patient_identity_id"],
    )

    op.create_table(
        "laboratory_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("laboratory_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("laboratory_specimen_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.Column("interpretation", sa.String(length=16), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('FINAL','AMENDED','ENTERED_IN_ERROR')",
            name="lab_result_status",
        ),
        sa.CheckConstraint(
            "value_type IN ('NUMERIC','TEXT','BOOLEAN','CODED')",
            name="lab_result_value_type",
        ),
        sa.CheckConstraint(
            "interpretation IS NULL OR interpretation IN ('NORMAL','ABNORMAL','CRITICAL')",
            name="lab_result_interpretation",
        ),
        sa.CheckConstraint("char_length(code_system) > 0", name="lab_result_code_system_required"),
        sa.CheckConstraint("char_length(code) > 0", name="lab_result_code_required"),
        sa.CheckConstraint("version >= 1", name="lab_result_version_positive"),
        sa.CheckConstraint(_VALUE_SHAPE, name="lab_result_value_shape"),
        sa.CheckConstraint(
            "reference_range_low IS NULL OR reference_range_high IS NULL "
            "OR reference_range_high >= reference_range_low",
            name="lab_result_reference_range",
        ),
        sa.ForeignKeyConstraint(
            ["laboratory_order_id"],
            ["laboratory_orders.id"],
            name="fk_laboratory_results_order_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["laboratory_specimen_id"],
            ["laboratory_specimens.id"],
            name="fk_laboratory_results_specimen_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_laboratory_results_patient_identity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_laboratory_results_encounter_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_laboratory_results_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_laboratory_results_facility_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["clinical_provenances.id"],
            name="fk_laboratory_results_provenance_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_laboratory_results"),
    )
    op.create_index(
        "ix_laboratory_results_patient_identity_id", "laboratory_results", ["patient_identity_id"]
    )
    op.create_index("ix_laboratory_results_order_id", "laboratory_results", ["laboratory_order_id"])
    op.create_index(
        "ix_laboratory_results_specimen_id", "laboratory_results", ["laboratory_specimen_id"]
    )
    op.create_index("ix_laboratory_results_organization_id", "laboratory_results", ["organization_id"])

    op.execute("ALTER TABLE clinical_provenances DROP CONSTRAINT IF EXISTS clinical_provenance_subject;")
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

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_lab_order_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'laboratory_orders cannot be deleted';
            END IF;
            IF NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id
               OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
               OR NEW.code_system IS DISTINCT FROM OLD.code_system
               OR NEW.code IS DISTINCT FROM OLD.code
               OR NEW.code_display IS DISTINCT FROM OLD.code_display
               OR NEW.ordered_at IS DISTINCT FROM OLD.ordered_at
               OR NEW.recorder_id IS DISTINCT FROM OLD.recorder_id
               OR NEW.provenance_id IS DISTINCT FROM OLD.provenance_id THEN
                RAISE EXCEPTION 'laboratory order historical facts are immutable';
            END IF;
            IF OLD.status IN ('CANCELLED','ENTERED_IN_ERROR') THEN
                RAISE EXCEPTION 'terminal laboratory order is immutable';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status
               AND NOT (
                    (OLD.status = 'REGISTERED' AND NEW.status IN ('IN_PROGRESS','CANCELLED','ENTERED_IN_ERROR'))
                    OR (OLD.status = 'IN_PROGRESS' AND NEW.status = 'ENTERED_IN_ERROR')
               ) THEN
                RAISE EXCEPTION 'invalid laboratory order status transition';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_laboratory_orders_history_immutable
        BEFORE UPDATE OR DELETE ON laboratory_orders
        FOR EACH ROW
        EXECUTE FUNCTION prevent_lab_order_history_mutation();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_lab_specimen_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'laboratory_specimens cannot be deleted';
            END IF;
            IF NEW.laboratory_order_id IS DISTINCT FROM OLD.laboratory_order_id
               OR NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id
               OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
               OR NEW.specimen_type IS DISTINCT FROM OLD.specimen_type
               OR NEW.collected_at IS DISTINCT FROM OLD.collected_at
               OR NEW.recorder_id IS DISTINCT FROM OLD.recorder_id
               OR NEW.provenance_id IS DISTINCT FROM OLD.provenance_id THEN
                RAISE EXCEPTION 'laboratory specimen historical facts are immutable';
            END IF;
            IF OLD.status IN ('REJECTED','ENTERED_IN_ERROR') THEN
                RAISE EXCEPTION 'terminal laboratory specimen is immutable';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status
               AND NOT (
                    OLD.status = 'COLLECTED'
                    AND NEW.status IN ('REJECTED','ENTERED_IN_ERROR')
               ) THEN
                RAISE EXCEPTION 'invalid laboratory specimen status transition';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_laboratory_specimens_history_immutable
        BEFORE UPDATE OR DELETE ON laboratory_specimens
        FOR EACH ROW
        EXECUTE FUNCTION prevent_lab_specimen_history_mutation();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_lab_result_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'laboratory_results cannot be deleted';
            END IF;
            IF NEW.laboratory_order_id IS DISTINCT FROM OLD.laboratory_order_id
               OR NEW.laboratory_specimen_id IS DISTINCT FROM OLD.laboratory_specimen_id
               OR NEW.patient_identity_id IS DISTINCT FROM OLD.patient_identity_id
               OR NEW.encounter_id IS DISTINCT FROM OLD.encounter_id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
               OR NEW.code_system IS DISTINCT FROM OLD.code_system
               OR NEW.code IS DISTINCT FROM OLD.code
               OR NEW.code_display IS DISTINCT FROM OLD.code_display
               OR NEW.value_type IS DISTINCT FROM OLD.value_type
               OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
               OR NEW.recorder_id IS DISTINCT FROM OLD.recorder_id
               OR NEW.provenance_id IS DISTINCT FROM OLD.provenance_id THEN
                RAISE EXCEPTION 'laboratory result historical facts are immutable';
            END IF;
            IF OLD.status = 'ENTERED_IN_ERROR' THEN
                RAISE EXCEPTION 'entered-in-error laboratory result is immutable';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status
               AND NOT (
                    (OLD.status = 'FINAL' AND NEW.status IN ('AMENDED','ENTERED_IN_ERROR'))
                    OR (OLD.status = 'AMENDED' AND NEW.status = 'ENTERED_IN_ERROR')
               ) THEN
                RAISE EXCEPTION 'invalid laboratory result status transition';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_laboratory_results_history_immutable
        BEFORE UPDATE OR DELETE ON laboratory_results
        FOR EACH ROW
        EXECUTE FUNCTION prevent_lab_result_history_mutation();
        """
    )

    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'clinical.laboratory.order.create', 'Create laboratory orders'),
            (gen_random_uuid(), 'clinical.laboratory.order.read', 'Read laboratory orders'),
            (gen_random_uuid(), 'clinical.laboratory.order.update', 'Cancel laboratory orders'),
            (
                gen_random_uuid(),
                'clinical.laboratory.order.entered_in_error',
                'Mark laboratory orders entered in error'
            ),
            (gen_random_uuid(), 'clinical.laboratory.specimen.create', 'Collect laboratory specimens'),
            (gen_random_uuid(), 'clinical.laboratory.specimen.read', 'Read laboratory specimens'),
            (gen_random_uuid(), 'clinical.laboratory.specimen.update', 'Reject laboratory specimens'),
            (
                gen_random_uuid(),
                'clinical.laboratory.specimen.entered_in_error',
                'Mark laboratory specimens entered in error'
            ),
            (gen_random_uuid(), 'clinical.laboratory.result.create', 'Create laboratory results'),
            (gen_random_uuid(), 'clinical.laboratory.result.read', 'Read laboratory results'),
            (gen_random_uuid(), 'clinical.laboratory.result.update', 'Amend laboratory results'),
            (
                gen_random_uuid(),
                'clinical.laboratory.result.entered_in_error',
                'Mark laboratory results entered in error'
            );
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r
        JOIN permissions p ON (
            (r.code IN ('PLATFORM_ADMIN','CLINICIAN') AND p.code LIKE 'clinical.laboratory.%')
            OR (
                r.code IN ('ORG_ADMIN','AUDITOR')
                AND p.code IN (
                    'clinical.laboratory.order.read',
                    'clinical.laboratory.specimen.read',
                    'clinical.laboratory.result.read'
                )
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
            SELECT id FROM permissions WHERE code LIKE 'clinical.laboratory.%'
        );
        """
    )
    op.execute("DELETE FROM permissions WHERE code LIKE 'clinical.laboratory.%';")
    op.execute("DROP TRIGGER IF EXISTS trg_laboratory_results_history_immutable ON laboratory_results;")
    op.execute("DROP FUNCTION IF EXISTS prevent_lab_result_history_mutation();")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_laboratory_specimens_history_immutable ON laboratory_specimens;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_lab_specimen_history_mutation();")
    op.execute("DROP TRIGGER IF EXISTS trg_laboratory_orders_history_immutable ON laboratory_orders;")
    op.execute("DROP FUNCTION IF EXISTS prevent_lab_order_history_mutation();")
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
    op.drop_index("ix_laboratory_results_organization_id", table_name="laboratory_results")
    op.drop_index("ix_laboratory_results_specimen_id", table_name="laboratory_results")
    op.drop_index("ix_laboratory_results_order_id", table_name="laboratory_results")
    op.drop_index("ix_laboratory_results_patient_identity_id", table_name="laboratory_results")
    op.drop_table("laboratory_results")
    op.drop_index("ix_laboratory_specimens_patient_identity_id", table_name="laboratory_specimens")
    op.drop_index("ix_laboratory_specimens_order_id", table_name="laboratory_specimens")
    op.drop_table("laboratory_specimens")
    op.drop_index("ix_laboratory_orders_organization_id", table_name="laboratory_orders")
    op.drop_index("ix_laboratory_orders_encounter_id", table_name="laboratory_orders")
    op.drop_index("ix_laboratory_orders_patient_identity_id", table_name="laboratory_orders")
    op.drop_table("laboratory_orders")
