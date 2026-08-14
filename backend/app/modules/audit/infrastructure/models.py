from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class AuditEventModel(UUIDPrimaryKeyMixin, Base):
    """Infrastructure audit table. Insert-only. Not a clinical record."""

    __tablename__ = "audit_events"

    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    facility_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    patient_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_metadata: Mapped[dict[str, str]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    integrity_note: Mapped[str | None] = mapped_column(Text, nullable=True)
