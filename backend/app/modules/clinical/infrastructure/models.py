from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EncounterModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "encounters"
    __table_args__ = (
        Index("ix_encounters_patient_identity_id", "patient_identity_id"),
        Index("ix_encounters_organization_id", "organization_id"),
        Index("ix_encounters_started_at", "started_at"),
        Index("ix_encounters_status", "status"),
    )

    patient_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    facility_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("facilities.id", ondelete="RESTRICT"),
        nullable=True,
    )
    encounter_class: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    display_label: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason_system: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    provenance_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class EncounterParticipantModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "encounter_participants"
    __table_args__ = (Index("ix_encounter_participants_encounter_id", "encounter_id"),)

    encounter_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    participation_type: Mapped[str] = mapped_column(String(32), nullable=False)


class ClinicalNoteModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clinical_notes"
    __table_args__ = (
        Index("ix_clinical_notes_patient_identity_id", "patient_identity_id"),
        Index("ix_clinical_notes_encounter_id", "encounter_id"),
        Index("ix_clinical_notes_authored_at", "authored_at"),
    )

    patient_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encounter_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    facility_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("facilities.id", ondelete="RESTRICT"),
        nullable=True,
    )
    note_type: Mapped[str] = mapped_column(String(32), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    record_status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clinical_notes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    author_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class ClinicalProvenanceModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clinical_provenances"
    __table_args__ = (Index("ix_clinical_provenances_subject", "subject_type", "subject_id"),)

    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_facility_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verification_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    authorship_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    information_source: Mapped[str] = mapped_column(String(32), nullable=False)
