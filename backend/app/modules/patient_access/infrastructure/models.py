from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PatientAccountModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patient_accounts"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','DISABLED')", name="patient_account_status"),
        CheckConstraint("char_length(subject) > 0", name="patient_account_subject_required"),
        Index(
            "uq_patient_accounts_active_identity",
            "patient_identity_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    patient_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_identities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
