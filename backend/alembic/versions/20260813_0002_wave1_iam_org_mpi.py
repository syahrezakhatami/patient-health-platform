"""Wave 1 IAM, organization, and MPI identity schema.

Revision ID: 20260813_0002
Revises: 20260813_0001
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0002"
down_revision: str | None = "20260813_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("organization_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "organization_type IN ('HOSPITAL','CLINIC','LABORATORY','PHARMACY','NETWORK','OTHER')",
            name="organization_type",
        ),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="organization_status"),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("code", name="uq_organizations_code"),
    )

    op.create_table(
        "facilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("facility_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("address_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "facility_type IN ('HOSPITAL_SITE','CLINIC_SITE','LABORATORY_SITE','EMERGENCY_DEPARTMENT','PHARMACY_SITE','OTHER')",
            name="facility_type",
        ),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="facility_status"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_facilities_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_facilities"),
        sa.UniqueConstraint("organization_id", "code", name="uq_facilities_organization_code"),
    )
    op.create_index("ix_facilities_organization_id", "facilities", ["organization_id"])

    op.create_table(
        "organization_identifiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identifier_system", sa.String(length=128), nullable=False),
        sa.Column("identifier_value", sa.String(length=255), nullable=False),
        sa.Column("normalized_value", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_identifiers_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_identifiers"),
    )
    op.create_index(
        "ix_organization_identifiers_organization_id",
        "organization_identifiers",
        ["organization_id"],
    )
    op.create_index(
        "uq_organization_identifiers_system_normalized",
        "organization_identifiers",
        ["identifier_system", "normalized_value"],
        unique=True,
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','DISABLED')", name="user_status"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("subject", name="uq_users_subject"),
    )

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("code", name="uq_roles_code"),
    )

    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="fk_role_permissions_role_id_roles", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_role_permissions_permission_id_permissions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_role_permissions"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
    )

    op.create_table(
        "organization_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','REVOKED')", name="membership_status"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_organization_memberships_user_id_users", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_memberships_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_organization_memberships_facility_id_facilities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="fk_organization_memberships_role_id_roles", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_memberships"),
    )
    op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])
    op.create_index(
        "ix_organization_memberships_organization_id",
        "organization_memberships",
        ["organization_id"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_organization_memberships_user_org_role
        ON organization_memberships (user_id, organization_id, role_id)
        NULLS NOT DISTINCT
        WHERE status = 'ACTIVE'
        """
    )

    op.create_table(
        "patient_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("identity_kind", sa.String(length=32), nullable=False),
        sa.Column("display_label", sa.String(length=64), nullable=False),
        sa.Column("given_name", sa.String(length=255), nullable=True),
        sa.Column("family_name", sa.String(length=255), nullable=True),
        sa.Column("name_normalized", sa.String(length=512), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("administrative_sex", sa.String(length=16), nullable=True),
        sa.Column("surviving_identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "lifecycle_status IN ('ANONYMOUS','ACTIVE','MERGED','RETIRED')",
            name="identity_lifecycle",
        ),
        sa.CheckConstraint(
            "identity_kind IN ('STANDARD','ANONYMOUS','TEMPORARY')",
            name="identity_kind",
        ),
        sa.CheckConstraint(
            "administrative_sex IS NULL OR administrative_sex IN ('MALE','FEMALE','OTHER','UNKNOWN')",
            name="administrative_sex",
        ),
        sa.CheckConstraint("id <> surviving_identity_id", name="identity_not_self_surviving"),
        sa.ForeignKeyConstraint(
            ["surviving_identity_id"],
            ["patient_identities.id"],
            name="fk_patient_identities_surviving_identity_id_patient_identities",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_patient_identities"),
    )
    op.create_index("ix_patient_identities_lifecycle_status", "patient_identities", ["lifecycle_status"])
    op.create_index("ix_patient_identities_name_dob", "patient_identities", ["name_normalized", "birth_date"])

    op.create_table(
        "patient_identifiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("identifier_system", sa.String(length=128), nullable=False),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("identifier_value", sa.String(length=255), nullable=False),
        sa.Column("normalized_value", sa.String(length=255), nullable=False),
        sa.Column("matching_value", sa.String(length=255), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("verification_method", sa.String(length=64), nullable=True),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_system", sa.String(length=128), nullable=True),
        sa.Column("source_record_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "identifier_type IN ('NIK','BPJS','PASSPORT','DRIVERS_LICENSE','NATIONAL_ID','MRN','EXTERNAL','PHONE','EMAIL','OTHER')",
            name="identifier_type",
        ),
        sa.CheckConstraint(
            "verification_status IN ('UNVERIFIED','VERIFIED','REJECTED','EXPIRED')",
            name="identifier_verification_status",
        ),
        sa.ForeignKeyConstraint(
            ["patient_identity_id"],
            ["patient_identities.id"],
            name="fk_patient_identifiers_patient_identity_id_patient_identities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_patient_identifiers_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name="fk_patient_identifiers_facility_id_facilities",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_patient_identifiers"),
    )
    op.create_index("ix_patient_identifiers_patient_identity_id", "patient_identifiers", ["patient_identity_id"])
    op.create_index("ix_patient_identifiers_organization_id", "patient_identifiers", ["organization_id"])
    op.create_index(
        "ix_patient_identifiers_system_normalized",
        "patient_identifiers",
        ["identifier_system", "normalized_value"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_patient_identifiers_global_active
        ON patient_identifiers (identifier_system, normalized_value)
        WHERE organization_id IS NULL
          AND valid_to IS NULL
          AND verification_status NOT IN ('REJECTED', 'EXPIRED')
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_patient_identifiers_org_active
        ON patient_identifiers (identifier_system, organization_id, normalized_value)
        WHERE organization_id IS NOT NULL
          AND valid_to IS NULL
          AND verification_status NOT IN ('REJECTED', 'EXPIRED')
        """
    )

    op.create_table(
        "identity_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','RETIRED')", name="cluster_status"),
        sa.ForeignKeyConstraint(
            ["canonical_identity_id"],
            ["patient_identities.id"],
            name="fk_identity_clusters_canonical_identity_id_patient_identities",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_identity_clusters"),
    )

    op.create_table(
        "identity_cluster_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_status", sa.String(length=32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "membership_status IN ('ACTIVE','MERGED_IN','UNMERGED')",
            name="cluster_membership_status",
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["identity_clusters.id"],
            name="fk_identity_cluster_members_cluster_id_identity_clusters",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["patient_identities.id"],
            name="fk_identity_cluster_members_identity_id_patient_identities",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_identity_cluster_members"),
    )
    op.create_index("ix_identity_cluster_members_cluster_id", "identity_cluster_members", ["cluster_id"])
    op.create_index("ix_identity_cluster_members_identity_id", "identity_cluster_members", ["identity_id"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_identity_cluster_members_active_identity
        ON identity_cluster_members (identity_id)
        WHERE valid_to IS NULL AND membership_status = 'ACTIVE'
        """
    )

    op.create_table(
        "identity_match_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("left_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("right_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("review_decision", sa.String(length=32), nullable=True),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("left_identity_id <> right_identity_id", name="match_not_self"),
        sa.CheckConstraint(
            "decision IN ('NO_MATCH','POSSIBLE_MATCH','PROBABLE_MATCH','CONFIRMED_MATCH','REQUIRES_REVIEW')",
            name="match_decision",
        ),
        sa.CheckConstraint("status IN ('OPEN','REVIEWED','SUPERSEDED')", name="match_status"),
        sa.ForeignKeyConstraint(
            ["left_identity_id"],
            ["patient_identities.id"],
            name="fk_imc_left_identity_id_patient_identities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["right_identity_id"],
            ["patient_identities.id"],
            name="fk_imc_right_identity_id_patient_identities",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_identity_match_candidates"),
        sa.UniqueConstraint(
            "left_identity_id",
            "right_identity_id",
            name="uq_identity_match_candidates_open_pair",
        ),
    )
    op.create_index("ix_identity_match_candidates_status", "identity_match_candidates", ["status"])

    op.create_table(
        "identity_provenances",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_system", sa.String(length=128), nullable=True),
        sa.Column("source_record_id", sa.String(length=128), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_method", sa.String(length=64), nullable=True),
        sa.Column("authorship_kind", sa.String(length=32), nullable=False),
        sa.Column("information_source", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "subject_type IN ('PATIENT_IDENTITY','IDENTIFIER','MATCH_CANDIDATE','MERGE_OPERATION','IDENTITY_RESOLUTION')",
            name="provenance_subject_type",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_identity_provenances"),
    )
    op.create_index(
        "ix_identity_provenances_subject",
        "identity_provenances",
        ["subject_type", "subject_id"],
    )

    op.create_table(
        "identity_merge_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("related_merge_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_identity_id <> target_identity_id", name="merge_not_self"),
        sa.CheckConstraint("operation IN ('MERGE','UNMERGE')", name="merge_operation"),
        sa.CheckConstraint("status IN ('COMPLETED','REJECTED')", name="merge_status"),
        sa.CheckConstraint("char_length(reason) > 0", name="merge_reason_required"),
        sa.ForeignKeyConstraint(
            ["source_identity_id"],
            ["patient_identities.id"],
            name="fk_imo_source_identity_id_patient_identities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_identity_id"],
            ["patient_identities.id"],
            name="fk_imo_target_identity_id_patient_identities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["related_merge_id"],
            ["identity_merge_operations.id"],
            name="fk_imo_related_merge_id_identity_merge_ops",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_identity_merge_operations"),
        sa.UniqueConstraint("idempotency_key", name="uq_identity_merge_operations_idempotency_key"),
    )
    op.create_index(
        "ix_identity_merge_operations_source_target",
        "identity_merge_operations",
        ["source_identity_id", "target_identity_id"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_identity_history_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'identity history tables are insert-only';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_identity_merge_operations_immutable
        BEFORE UPDATE OR DELETE ON identity_merge_operations
        FOR EACH ROW
        EXECUTE FUNCTION prevent_identity_history_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_identity_provenances_immutable
        BEFORE UPDATE OR DELETE ON identity_provenances
        FOR EACH ROW
        EXECUTE FUNCTION prevent_identity_history_mutation();
        """
    )

    _seed_roles_and_permissions()


def _seed_roles_and_permissions() -> None:
    op.execute(
        """
        INSERT INTO roles (id, code, name) VALUES
            (gen_random_uuid(), 'PLATFORM_ADMIN', 'Platform administrator'),
            (gen_random_uuid(), 'ORG_ADMIN', 'Organization administrator'),
            (gen_random_uuid(), 'REGISTRAR', 'Registrar'),
            (gen_random_uuid(), 'IDENTITY_OFFICER', 'Identity officer'),
            (gen_random_uuid(), 'AUDITOR', 'Auditor');
        """
    )
    op.execute(
        """
        INSERT INTO permissions (id, code, description) VALUES
            (gen_random_uuid(), 'iam.platform', 'Platform-wide authorization scope'),
            (gen_random_uuid(), 'iam.user.read', 'Read provisioned users'),
            (gen_random_uuid(), 'iam.user.provision', 'Provision users'),
            (gen_random_uuid(), 'iam.membership.manage', 'Manage organization memberships'),
            (gen_random_uuid(), 'org.organization.create', 'Create organizations'),
            (gen_random_uuid(), 'org.organization.read', 'Read organizations'),
            (gen_random_uuid(), 'org.facility.create', 'Create facilities'),
            (gen_random_uuid(), 'org.facility.read', 'Read facilities'),
            (gen_random_uuid(), 'org.identifier.manage', 'Manage organization identifiers'),
            (gen_random_uuid(), 'mpi.identity.create', 'Create patient identities'),
            (gen_random_uuid(), 'mpi.identity.read', 'Read patient identities'),
            (gen_random_uuid(), 'mpi.identifier.add', 'Add patient identifiers'),
            (gen_random_uuid(), 'mpi.identifier.verify', 'Verify or reject identifiers'),
            (gen_random_uuid(), 'mpi.match.evaluate', 'Evaluate identity matches'),
            (gen_random_uuid(), 'mpi.match.review', 'Review match candidates'),
            (gen_random_uuid(), 'mpi.merge.execute', 'Execute identity merge'),
            (gen_random_uuid(), 'mpi.unmerge.execute', 'Execute identity unmerge');
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r
        JOIN permissions p ON (
            (r.code = 'PLATFORM_ADMIN')
            OR (r.code = 'ORG_ADMIN' AND p.code IN (
                'iam.user.read','iam.membership.manage','org.organization.read',
                'org.facility.create','org.facility.read','org.identifier.manage','mpi.identity.read'
            ))
            OR (r.code = 'REGISTRAR' AND p.code IN (
                'iam.user.read','org.organization.read','org.facility.read',
                'mpi.identity.create','mpi.identity.read','mpi.identifier.add','mpi.match.evaluate'
            ))
            OR (r.code = 'IDENTITY_OFFICER' AND p.code IN (
                'iam.user.read','org.organization.read','org.facility.read',
                'mpi.identity.create','mpi.identity.read','mpi.identifier.add','mpi.identifier.verify',
                'mpi.match.evaluate','mpi.match.review','mpi.merge.execute','mpi.unmerge.execute'
            ))
            OR (r.code = 'AUDITOR' AND p.code IN (
                'iam.user.read','org.organization.read','org.facility.read','mpi.identity.read'
            ))
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_identity_provenances_immutable ON identity_provenances;")
    op.execute("DROP TRIGGER IF EXISTS trg_identity_merge_operations_immutable ON identity_merge_operations;")
    op.execute("DROP FUNCTION IF EXISTS prevent_identity_history_mutation();")
    op.drop_table("identity_merge_operations")
    op.drop_table("identity_provenances")
    op.drop_table("identity_match_candidates")
    op.drop_table("identity_cluster_members")
    op.drop_table("identity_clusters")
    op.drop_table("patient_identifiers")
    op.drop_table("patient_identities")
    op.drop_table("organization_memberships")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_table("organization_identifiers")
    op.drop_table("facilities")
    op.drop_table("organizations")
