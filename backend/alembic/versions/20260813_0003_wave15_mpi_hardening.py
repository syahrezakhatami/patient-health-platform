"""Wave 1.5 MPI hardening: match probes.

Revision ID: 20260813_0003
Revises: 20260813_0002
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0003"
down_revision: str | None = "20260813_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "identity_match_probes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("score", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("evidence_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose IN ("
            "'REGISTRATION','IDENTITY_RESOLUTION','EMERGENCY','CARE_COORDINATION',"
            "'ADMINISTRATION','PATIENT_ACCESS','AUDIT','SYSTEM_OPERATION')",
            name="match_probe_purpose",
        ),
        sa.CheckConstraint(
            "status IN ('PROBE_ONLY','MATCHED_CANDIDATE')",
            name="match_probe_status",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_identity_id"],
            ["patient_identities.id"],
            name="fk_identity_match_probes_candidate_identity_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_identity_match_probes"),
    )
    op.create_index(
        "ix_identity_match_probes_candidate",
        "identity_match_probes",
        ["candidate_identity_id"],
    )
    op.create_index(
        "ix_identity_match_probes_organization",
        "identity_match_probes",
        ["organization_id"],
    )
    op.create_index(
        "ix_identity_match_probes_occurred_at",
        "identity_match_probes",
        ["occurred_at"],
    )
    op.execute(
        """
        CREATE TRIGGER trg_identity_match_probes_immutable
        BEFORE UPDATE OR DELETE ON identity_match_probes
        FOR EACH ROW
        EXECUTE FUNCTION prevent_identity_history_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_identity_match_probes_immutable ON identity_match_probes;")
    op.drop_index("ix_identity_match_probes_occurred_at", table_name="identity_match_probes")
    op.drop_index("ix_identity_match_probes_organization", table_name="identity_match_probes")
    op.drop_index("ix_identity_match_probes_candidate", table_name="identity_match_probes")
    op.drop_table("identity_match_probes")
