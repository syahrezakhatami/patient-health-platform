"""Clinical observation write idempotency for Manual Vital Signs.

Revision ID: 20260814_0021
Revises: 20260814_0020
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0021"
down_revision: str | None = "20260814_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinical_observation_write_idempotency",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.CHAR(length=64), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation IN ('OBSERVATION_CREATE')",
            name="clinical_observation_write_idempotency_operation",
        ),
        sa.CheckConstraint(
            "char_length(idempotency_key) >= 8 AND char_length(idempotency_key) <= 128",
            name="clinical_observation_write_idempotency_key_length",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_clinical_observation_write_idempotency_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["observations.id"],
            name="fk_clinical_observation_write_idempotency_observation_id",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clinical_observation_write_idempotency"),
        sa.UniqueConstraint(
            "organization_id",
            "actor_id",
            "operation",
            "idempotency_key",
            name="uq_clinical_observation_write_idempotency_scope",
        ),
    )
    op.create_index(
        "ix_clinical_observation_write_idempotency_observation_id",
        "clinical_observation_write_idempotency",
        ["observation_id"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_clinical_observation_write_idempotency_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'clinical observation write idempotency is immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_clinical_observation_write_idempotency_immutable
        BEFORE UPDATE OR DELETE ON clinical_observation_write_idempotency
        FOR EACH ROW
        EXECUTE FUNCTION prevent_clinical_observation_write_idempotency_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_clinical_observation_write_idempotency_immutable "
        "ON clinical_observation_write_idempotency;"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prevent_clinical_observation_write_idempotency_mutation();"
    )
    op.drop_index(
        "ix_clinical_observation_write_idempotency_observation_id",
        table_name="clinical_observation_write_idempotency",
    )
    op.drop_table("clinical_observation_write_idempotency")
