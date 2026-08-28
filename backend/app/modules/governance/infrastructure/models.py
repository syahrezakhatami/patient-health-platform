from datetime import date, datetime
from uuid import UUID

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class ProviderCapabilityModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "provider_capabilities"
    __table_args__ = (
        UniqueConstraint("feature_id", name="uq_provider_capabilities_feature_id"),
        CheckConstraint(
            "provider_state IN ('AVAILABLE','SUSPENDED','RETIRED')",
            name="provider_capabilities_state",
        ),
        Index("ix_provider_capabilities_feature_id", "feature_id"),
    )

    feature_id: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    frozen_release_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_state: Mapped[str] = mapped_column(String(32), nullable=False)
    governance_required: Mapped[bool] = mapped_column(nullable=False, default=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ProviderCapabilityRequiredGateModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "provider_capability_required_gates"
    __table_args__ = (
        UniqueConstraint(
            "provider_capability_id",
            "gate_type",
            name="uq_provider_capability_required_gates_capability_gate",
        ),
        CheckConstraint(
            "gate_type IN ('CONTROLLER_PROCESSOR_ASSESSMENT','DPA')",
            name="provider_capability_required_gates_type",
        ),
    )

    provider_capability_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provider_capabilities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )


class OrganizationGovernanceProfileModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_governance_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_organization_governance_profiles_org"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    active_published_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "organization_governance_profile_versions.id",
            name="fk_organization_governance_profiles_active_version_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )


class OrganizationGovernanceProfileVersionModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "organization_governance_profile_versions"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "version_number",
            name="uq_organization_governance_profile_versions_profile_version",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','SUPERSEDED')",
            name="organization_governance_profile_versions_status",
        ),
    )

    profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organization_governance_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    policy_document: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    previous_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organization_governance_profile_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )


class OrganizationFeatureActivationModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_feature_activations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider_capability_id",
            name="uq_organization_feature_activations_org_capability",
        ),
        CheckConstraint(
            "activation_state IN ('PENDING_APPROVAL','APPROVED','ACTIVE','SUSPENDED','RETIRED')",
            name="organization_feature_activations_state",
        ),
        Index("ix_organization_feature_activations_org_feature", "organization_id", "feature_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_capability_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provider_capabilities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    feature_id: Mapped[str] = mapped_column(String(128), nullable=False)
    activation_state: Mapped[str] = mapped_column(String(32), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class OrganizationDeploymentGateStateModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_deployment_gate_states"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "gate_type",
            name="uq_organization_deployment_gate_states_org_gate",
        ),
        CheckConstraint(
            "gate_type IN ('CONTROLLER_PROCESSOR_ASSESSMENT','DPA')",
            name="organization_deployment_gate_states_type",
        ),
        CheckConstraint(
            "gate_state IN ('NOT_ASSESSED','PENDING','SATISFIED','NOT_APPLICABLE','EXPIRED')",
            name="organization_deployment_gate_states_state",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_state: Mapped[str] = mapped_column(String(32), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class GovernanceApprovalEvidenceModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "governance_approval_evidence"
    __table_args__ = (
        CheckConstraint(
            "status IN ('APPROVED','REJECTED','WITHDRAWN','SUPERSEDED')",
            name="governance_approval_evidence_status",
        ),
        Index("ix_governance_approval_evidence_org_feature", "organization_id", "feature_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_capability_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provider_capabilities.id", ondelete="RESTRICT"),
        nullable=True,
    )
    feature_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    governance_profile_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organization_governance_profile_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    approval_type: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approval_date: Mapped[date] = mapped_column(Date, nullable=False)
    artifact_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    approver_role_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    supersedes_evidence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("governance_approval_evidence.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )


class GovernanceAdminIdempotencyModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "governance_admin_idempotency"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('ORGANIZATION','PLATFORM')",
            name="governance_admin_idempotency_scope_type",
        ),
        CheckConstraint(
            "char_length(idempotency_key) >= 8 AND char_length(idempotency_key) <= 128",
            name="governance_admin_idempotency_key_length",
        ),
        Index(
            "uq_governance_admin_idempotency_org_scope",
            "organization_id",
            "actor_id",
            "operation",
            "idempotency_key",
            unique=True,
            postgresql_where="scope_type = 'ORGANIZATION'",
        ),
        Index(
            "uq_governance_admin_idempotency_platform_scope",
            "actor_id",
            "operation",
            "idempotency_key",
            unique=True,
            postgresql_where="scope_type = 'PLATFORM'",
        ),
    )

    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    actor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
