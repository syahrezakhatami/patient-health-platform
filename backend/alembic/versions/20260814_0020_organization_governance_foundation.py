"""Organization governance profile foundation.

Revision ID: 20260814_0020
Revises: 20260814_0019
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0020"
down_revision: str | None = "20260814_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_id", sa.String(length=128), nullable=False),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column("frozen_release_tag", sa.String(length=128), nullable=True),
        sa.Column("provider_state", sa.String(length=32), nullable=False),
        sa.Column("governance_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider_state IN ('AVAILABLE','SUSPENDED','RETIRED')",
            name="provider_capabilities_state",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_capabilities"),
        sa.UniqueConstraint("feature_id", name="uq_provider_capabilities_feature_id"),
    )
    op.create_index("ix_provider_capabilities_feature_id", "provider_capabilities", ["feature_id"])

    op.create_table(
        "provider_capability_required_gates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_capability_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gate_type", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "gate_type IN ('CONTROLLER_PROCESSOR_ASSESSMENT','DPA')",
            name="provider_capability_required_gates_type",
        ),
        sa.ForeignKeyConstraint(
            ["provider_capability_id"],
            ["provider_capabilities.id"],
            name="fk_provider_capability_required_gates_capability_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_capability_required_gates"),
        sa.UniqueConstraint(
            "provider_capability_id",
            "gate_type",
            name="uq_provider_capability_required_gates_capability_gate",
        ),
    )

    op.create_table(
        "organization_governance_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_published_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_governance_profiles_organization_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_governance_profiles"),
        sa.UniqueConstraint(
            "organization_id",
            name="uq_organization_governance_profiles_org",
        ),
    )

    op.create_table(
        "organization_governance_profile_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("policy_document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("previous_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','SUPERSEDED')",
            name="organization_governance_profile_versions_status",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["organization_governance_profiles.id"],
            name="fk_organization_governance_profile_versions_profile_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_governance_profile_versions_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name="fk_organization_governance_profile_versions_changed_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_version_id"],
            ["organization_governance_profile_versions.id"],
            name="fk_organization_governance_profile_versions_previous_version_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_governance_profile_versions"),
        sa.UniqueConstraint(
            "profile_id",
            "version_number",
            name="uq_organization_governance_profile_versions_profile_version",
        ),
    )

    op.create_foreign_key(
        "fk_organization_governance_profiles_active_version_id",
        "organization_governance_profiles",
        "organization_governance_profile_versions",
        ["active_published_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "organization_feature_activations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_capability_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_id", sa.String(length=128), nullable=False),
        sa.Column("activation_state", sa.String(length=32), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "activation_state IN ('PENDING_APPROVAL','APPROVED','ACTIVE','SUSPENDED','RETIRED')",
            name="organization_feature_activations_state",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_feature_activations_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_capability_id"],
            ["provider_capabilities.id"],
            name="fk_organization_feature_activations_capability_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_feature_activations"),
        sa.UniqueConstraint(
            "organization_id",
            "provider_capability_id",
            name="uq_organization_feature_activations_org_capability",
        ),
    )
    op.create_index(
        "ix_organization_feature_activations_org_feature",
        "organization_feature_activations",
        ["organization_id", "feature_id"],
    )

    op.create_table(
        "organization_deployment_gate_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gate_type", sa.String(length=64), nullable=False),
        sa.Column("gate_state", sa.String(length=32), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "gate_type IN ('CONTROLLER_PROCESSOR_ASSESSMENT','DPA')",
            name="organization_deployment_gate_states_type",
        ),
        sa.CheckConstraint(
            "gate_state IN ('NOT_ASSESSED','PENDING','SATISFIED','NOT_APPLICABLE','EXPIRED')",
            name="organization_deployment_gate_states_state",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_deployment_gate_states_organization_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_deployment_gate_states"),
        sa.UniqueConstraint(
            "organization_id",
            "gate_type",
            name="uq_organization_deployment_gate_states_org_gate",
        ),
    )

    op.create_table(
        "governance_approval_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_capability_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feature_id", sa.String(length=128), nullable=False),
        sa.Column("provider_feature_version", sa.String(length=64), nullable=False),
        sa.Column("governance_profile_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_type", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("decision_by_name", sa.String(length=255), nullable=False),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_date", sa.Date(), nullable=False),
        sa.Column("artifact_reference", sa.String(length=512), nullable=True),
        sa.Column("approver_role_category", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("supersedes_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('APPROVED','REJECTED','WITHDRAWN','SUPERSEDED')",
            name="governance_approval_evidence_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_governance_approval_evidence_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_capability_id"],
            ["provider_capabilities.id"],
            name="fk_governance_approval_evidence_capability_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["governance_profile_version_id"],
            ["organization_governance_profile_versions.id"],
            name="fk_governance_approval_evidence_profile_version_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
            name="fk_governance_approval_evidence_recorded_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_evidence_id"],
            ["governance_approval_evidence.id"],
            name="fk_governance_approval_evidence_supersedes_evidence_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_governance_approval_evidence"),
    )
    op.create_index(
        "ix_governance_approval_evidence_org_feature",
        "governance_approval_evidence",
        ["organization_id", "feature_id"],
    )

    op.create_table(
        "governance_admin_idempotency",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.CHAR(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "scope_type IN ('ORGANIZATION','PLATFORM')",
            name="governance_admin_idempotency_scope_type",
        ),
        sa.CheckConstraint(
            "char_length(idempotency_key) >= 8 AND char_length(idempotency_key) <= 128",
            name="governance_admin_idempotency_key_length",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_governance_admin_idempotency_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_governance_admin_idempotency_actor_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_governance_admin_idempotency"),
    )
    op.create_index(
        "uq_governance_admin_idempotency_org_scope",
        "governance_admin_idempotency",
        ["organization_id", "actor_id", "operation", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("scope_type = 'ORGANIZATION'"),
    )
    op.create_index(
        "uq_governance_admin_idempotency_platform_scope",
        "governance_admin_idempotency",
        ["actor_id", "operation", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("scope_type = 'PLATFORM'"),
    )

    _create_triggers()
    _seed_permissions()


def _create_triggers() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_governance_admin_idempotency_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'governance admin idempotency is immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_governance_admin_idempotency_immutable
        BEFORE UPDATE OR DELETE ON governance_admin_idempotency
        FOR EACH ROW
        EXECUTE FUNCTION prevent_governance_admin_idempotency_mutation();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_governance_approval_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'governance approval evidence is immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_governance_approval_evidence_immutable
        BEFORE UPDATE OR DELETE ON governance_approval_evidence
        FOR EACH ROW
        EXECUTE FUNCTION prevent_governance_approval_evidence_mutation();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_published_profile_version_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'governance profile versions cannot be deleted';
            END IF;
            IF OLD.status = 'PUBLISHED' AND NEW.status = 'SUPERSEDED'
               AND NEW.profile_id = OLD.profile_id
               AND NEW.organization_id = OLD.organization_id
               AND NEW.version_number = OLD.version_number
               AND NEW.schema_version = OLD.schema_version
               AND NEW.policy_document = OLD.policy_document
               AND NEW.effective_at = OLD.effective_at
               AND NEW.changed_by = OLD.changed_by
               AND NEW.changed_at = OLD.changed_at
               AND NEW.reason = OLD.reason
               AND NEW.previous_version_id IS NOT DISTINCT FROM OLD.previous_version_id THEN
                RETURN NEW;
            END IF;
            IF OLD.status IN ('PUBLISHED','SUPERSEDED') THEN
                RAISE EXCEPTION 'published governance profile versions are immutable';
            END IF;
            IF NEW.profile_id IS DISTINCT FROM OLD.profile_id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
                RAISE EXCEPTION 'governance profile version bindings are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_organization_governance_profile_versions_immutable
        BEFORE UPDATE OR DELETE ON organization_governance_profile_versions
        FOR EACH ROW
        EXECUTE FUNCTION prevent_published_profile_version_mutation();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_governance_profile_binding_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'governance profiles cannot be deleted';
            END IF;
            IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
                RAISE EXCEPTION 'governance profile organization binding is immutable';
            END IF;
            IF NEW.active_published_version_id IS NOT NULL THEN
                IF NOT EXISTS (
                    SELECT 1
                    FROM organization_governance_profile_versions v
                    WHERE v.id = NEW.active_published_version_id
                      AND v.profile_id = NEW.id
                      AND v.organization_id = NEW.organization_id
                      AND v.status = 'PUBLISHED'
                ) THEN
                    RAISE EXCEPTION 'active published version must belong to same profile and organization';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_organization_governance_profiles_binding
        BEFORE UPDATE OR DELETE ON organization_governance_profiles
        FOR EACH ROW
        EXECUTE FUNCTION prevent_governance_profile_binding_mutation();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_feature_activation_binding_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'feature activations cannot be deleted';
            END IF;
            IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.provider_capability_id IS DISTINCT FROM OLD.provider_capability_id
               OR NEW.feature_id IS DISTINCT FROM OLD.feature_id THEN
                RAISE EXCEPTION 'feature activation bindings are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_organization_feature_activations_binding
        BEFORE UPDATE OR DELETE ON organization_feature_activations
        FOR EACH ROW
        EXECUTE FUNCTION prevent_feature_activation_binding_mutation();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_provider_capability_seed_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'provider capabilities cannot be deleted';
            END IF;
            IF NEW.feature_id IS DISTINCT FROM OLD.feature_id
               OR NEW.feature_version IS DISTINCT FROM OLD.feature_version
               OR NEW.governance_required IS DISTINCT FROM OLD.governance_required
               OR NEW.frozen_release_tag IS DISTINCT FROM OLD.frozen_release_tag THEN
                RAISE EXCEPTION 'provider capability identity metadata is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_provider_capabilities_seed_immutable
        BEFORE UPDATE OR DELETE ON provider_capabilities
        FOR EACH ROW
        EXECUTE FUNCTION prevent_provider_capability_seed_mutation();
        """
    )


def _seed_permissions() -> None:
    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'governance.profile.read', 'Read organization governance profile'),
            (gen_random_uuid(), 'governance.profile.manage', 'Manage organization governance profile'),
            (gen_random_uuid(), 'governance.approval.record', 'Record governance approval evidence'),
            (gen_random_uuid(), 'governance.feature.activate', 'Transition organization feature activation'),
            (gen_random_uuid(), 'governance.provider.manage', 'Manage provider capability registry');
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r
        JOIN permissions p ON (
            (r.code = 'PLATFORM_ADMIN' AND p.code = 'governance.provider.manage')
            OR (
                r.code = 'ORG_ADMIN'
                AND p.code IN ('governance.profile.read', 'governance.profile.manage')
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
            SELECT id FROM permissions WHERE code LIKE 'governance.%'
        );
        """
    )
    op.execute("DELETE FROM permissions WHERE code LIKE 'governance.%';")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_provider_capabilities_seed_immutable ON provider_capabilities;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_provider_capability_seed_mutation();")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_organization_feature_activations_binding "
        "ON organization_feature_activations;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_feature_activation_binding_mutation();")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_organization_governance_profiles_binding "
        "ON organization_governance_profiles;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_governance_profile_binding_mutation();")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_organization_governance_profile_versions_immutable "
        "ON organization_governance_profile_versions;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_published_profile_version_mutation();")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_governance_approval_evidence_immutable "
        "ON governance_approval_evidence;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_governance_approval_evidence_mutation();")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_governance_admin_idempotency_immutable "
        "ON governance_admin_idempotency;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_governance_admin_idempotency_mutation();")

    op.drop_index(
        "uq_governance_admin_idempotency_platform_scope",
        table_name="governance_admin_idempotency",
    )
    op.drop_index(
        "uq_governance_admin_idempotency_org_scope",
        table_name="governance_admin_idempotency",
    )
    op.drop_table("governance_admin_idempotency")
    op.drop_index(
        "ix_governance_approval_evidence_org_feature",
        table_name="governance_approval_evidence",
    )
    op.drop_table("governance_approval_evidence")
    op.drop_table("organization_deployment_gate_states")
    op.drop_index(
        "ix_organization_feature_activations_org_feature",
        table_name="organization_feature_activations",
    )
    op.drop_table("organization_feature_activations")
    op.drop_constraint(
        "fk_organization_governance_profiles_active_version_id",
        "organization_governance_profiles",
        type_="foreignkey",
    )
    op.drop_table("organization_governance_profile_versions")
    op.drop_table("organization_governance_profiles")
    op.drop_table("provider_capability_required_gates")
    op.drop_index("ix_provider_capabilities_feature_id", table_name="provider_capabilities")
    op.drop_table("provider_capabilities")
