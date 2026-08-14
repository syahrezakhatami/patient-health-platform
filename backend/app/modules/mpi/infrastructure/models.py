from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PatientIdentityModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patient_identities"

    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    identity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    display_label: Mapped[str] = mapped_column(String(64), nullable=False)
    given_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    family_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_normalized: Mapped[str | None] = mapped_column(String(512), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    administrative_sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    surviving_identity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=True,
    )


class PatientIdentifierModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patient_identifiers"

    patient_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    facility_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("facilities.id", ondelete="RESTRICT"),
        nullable=True,
    )
    identifier_system: Mapped[str] = mapped_column(String(128), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(255), nullable=False)
    matching_value: Mapped[str] = mapped_column(String(255), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    verification_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class IdentityClusterModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "identity_clusters"

    canonical_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class IdentityClusterMemberModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "identity_cluster_members"

    cluster_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity_clusters.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    membership_status: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdentityMatchCandidateModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "identity_match_candidates"
    __table_args__ = (
        UniqueConstraint(
            "left_identity_id",
            "right_identity_id",
            name="uq_identity_match_candidates_open_pair",
        ),
        Index("ix_identity_match_candidates_status", "status"),
    )

    left_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    right_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    score: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    review_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class IdentityMergeOperationModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "identity_merge_operations"
    __table_args__ = (
        Index(
            "ix_identity_merge_operations_source_target",
            "source_identity_id",
            "target_identity_id",
        ),
        UniqueConstraint("idempotency_key", name="uq_identity_merge_operations_idempotency_key"),
    )

    source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    facility_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    evidence: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    related_merge_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity_merge_operations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provenance_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdentityMatchProbeModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "identity_match_probes"
    __table_args__ = (
        Index("ix_identity_match_probes_candidate", "candidate_identity_id"),
        Index("ix_identity_match_probes_organization", "organization_id"),
        Index("ix_identity_match_probes_occurred_at", "occurred_at"),
    )

    candidate_identity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=True,
    )
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    facility_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    score: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    evidence_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provenance_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdentityProvenanceModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "identity_provenances"
    __table_args__ = (Index("ix_identity_provenances_subject", "subject_type", "subject_id"),)

    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_facility_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    authorship_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    information_source: Mapped[str] = mapped_column(String(32), nullable=False)
