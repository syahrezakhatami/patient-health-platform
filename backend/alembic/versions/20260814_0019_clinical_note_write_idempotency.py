"""Clinical note write idempotency and attribution immutability.

Revision ID: 20260814_0019
Revises: 20260814_0018
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0019"
down_revision: str | None = "20260814_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NOTE_TRIGGER = """
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
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
       OR NEW.author_id IS DISTINCT FROM OLD.author_id
       OR NEW.note_type IS DISTINCT FROM OLD.note_type THEN
        RAISE EXCEPTION 'clinical note attribution is immutable';
    END IF;
    IF OLD.record_status = 'ENTERED_IN_ERROR' THEN
        RAISE EXCEPTION 'entered-in-error clinical note is immutable';
    END IF;
    IF OLD.record_status = 'FINAL' AND (
        NEW.body_text IS DISTINCT FROM OLD.body_text
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

_NOTE_TRIGGER_0005 = """
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


def upgrade() -> None:
    op.create_table(
        "clinical_note_write_idempotency",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.CHAR(length=64), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation IN ('NOTE_CREATE','NOTE_FINALIZE')",
            name="clinical_note_write_idempotency_operation",
        ),
        sa.CheckConstraint(
            "char_length(idempotency_key) >= 8 AND char_length(idempotency_key) <= 128",
            name="clinical_note_write_idempotency_key_length",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_clinical_note_write_idempotency_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["clinical_notes.id"],
            name="fk_clinical_note_write_idempotency_note_id",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clinical_note_write_idempotency"),
        sa.UniqueConstraint(
            "organization_id",
            "actor_id",
            "operation",
            "idempotency_key",
            name="uq_clinical_note_write_idempotency_scope",
        ),
    )
    op.create_index(
        "ix_clinical_note_write_idempotency_note_id",
        "clinical_note_write_idempotency",
        ["note_id"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_clinical_note_write_idempotency_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'clinical note write idempotency is immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_clinical_note_write_idempotency_immutable
        BEFORE UPDATE OR DELETE ON clinical_note_write_idempotency
        FOR EACH ROW
        EXECUTE FUNCTION prevent_clinical_note_write_idempotency_mutation();
        """
    )
    op.execute(_NOTE_TRIGGER)


def downgrade() -> None:
    op.execute(_NOTE_TRIGGER_0005)
    op.execute(
        "DROP TRIGGER IF EXISTS trg_clinical_note_write_idempotency_immutable "
        "ON clinical_note_write_idempotency;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_clinical_note_write_idempotency_mutation();")
    op.drop_index(
        "ix_clinical_note_write_idempotency_note_id",
        table_name="clinical_note_write_idempotency",
    )
    op.drop_table("clinical_note_write_idempotency")
