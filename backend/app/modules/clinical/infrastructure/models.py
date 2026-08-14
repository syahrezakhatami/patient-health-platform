from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
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


class ConditionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conditions"
    __table_args__ = (
        Index("ix_conditions_patient_identity_id", "patient_identity_id"),
        Index("ix_conditions_encounter_id", "encounter_id"),
        Index("ix_conditions_organization_id", "organization_id"),
        Index("ix_conditions_recorded_at", "recorded_at"),
    )

    patient_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="RESTRICT"),
        nullable=True,
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
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    code_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clinical_status: Mapped[str] = mapped_column(String(32), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    onset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    abatement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorder_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    provenance_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clinical_provenances.id", ondelete="RESTRICT"),
        nullable=True,
    )


class ObservationModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_observations_patient_identity_id", "patient_identity_id"),
        Index("ix_observations_encounter_id", "encounter_id"),
        Index("ix_observations_organization_id", "organization_id"),
        Index("ix_observations_recorded_at", "recorded_at"),
    )

    patient_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="RESTRICT"),
        nullable=True,
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
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    code_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_code_system: Mapped[str | None] = mapped_column(String(128), nullable=True)
    value_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    value_code_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_range_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    reference_range_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorder_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clinical_provenances.id", ondelete="RESTRICT"),
        nullable=True,
    )


class LaboratoryOrderModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "laboratory_orders"
    __table_args__ = (
        Index("ix_laboratory_orders_patient_identity_id", "patient_identity_id"),
        Index("ix_laboratory_orders_encounter_id", "encounter_id"),
        Index("ix_laboratory_orders_organization_id", "organization_id"),
    )

    patient_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="RESTRICT"),
        nullable=True,
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
    code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    code_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorder_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clinical_provenances.id", ondelete="RESTRICT"),
        nullable=True,
    )


class LaboratorySpecimenModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "laboratory_specimens"
    __table_args__ = (
        Index("ix_laboratory_specimens_order_id", "laboratory_order_id"),
        Index("ix_laboratory_specimens_patient_identity_id", "patient_identity_id"),
    )

    laboratory_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("laboratory_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    patient_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="RESTRICT"),
        nullable=True,
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
    specimen_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorder_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    provenance_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clinical_provenances.id", ondelete="RESTRICT"),
        nullable=True,
    )


class LaboratoryResultModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "laboratory_results"
    __table_args__ = (
        Index("ix_laboratory_results_patient_identity_id", "patient_identity_id"),
        Index("ix_laboratory_results_order_id", "laboratory_order_id"),
        Index("ix_laboratory_results_specimen_id", "laboratory_specimen_id"),
        Index("ix_laboratory_results_organization_id", "organization_id"),
    )

    laboratory_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("laboratory_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    laboratory_specimen_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("laboratory_specimens.id", ondelete="RESTRICT"),
        nullable=False,
    )
    patient_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="RESTRICT"),
        nullable=True,
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
    code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    code_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_code_system: Mapped[str | None] = mapped_column(String(128), nullable=True)
    value_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    value_code_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_range_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    reference_range_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    interpretation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorder_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clinical_provenances.id", ondelete="RESTRICT"),
        nullable=True,
    )
