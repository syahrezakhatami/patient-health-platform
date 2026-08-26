from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.patient_access.domain.enums import PatientAccountStatus
from app.modules.patient_access.domain.models import PatientAccount
from app.modules.patient_access.infrastructure.models import PatientAccountModel


class PatientAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, model: PatientAccountModel) -> PatientAccountModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get(self, account_id: UUID) -> PatientAccount | None:
        row = await self._session.get(PatientAccountModel, account_id)
        return _to_account(row) if row is not None else None

    async def get_by_subject(self, subject: str) -> PatientAccount | None:
        row = await self.get_model_by_subject_for_update(subject, lock=False)
        return _to_account(row) if row is not None else None

    async def get_active_by_identity(self, patient_identity_id: UUID) -> PatientAccount | None:
        row = await self.get_active_model_by_identity_for_update(patient_identity_id, lock=False)
        return _to_account(row) if row is not None else None

    async def get_model(self, account_id: UUID) -> PatientAccountModel | None:
        return await self._session.get(PatientAccountModel, account_id)

    async def get_model_for_update(self, account_id: UUID) -> PatientAccountModel | None:
        result = await self._session.execute(
            select(PatientAccountModel)
            .where(PatientAccountModel.id == account_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_model_by_subject_for_update(
        self, subject: str, *, lock: bool = True
    ) -> PatientAccountModel | None:
        stmt = select(PatientAccountModel).where(PatientAccountModel.subject == subject)
        if lock:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_model_by_identity_for_update(
        self, patient_identity_id: UUID, *, lock: bool = True
    ) -> PatientAccountModel | None:
        stmt = select(PatientAccountModel).where(
            PatientAccountModel.patient_identity_id == patient_identity_id,
            PatientAccountModel.status == PatientAccountStatus.ACTIVE,
        )
        if lock:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


def _to_account(row: PatientAccountModel) -> PatientAccount:
    return PatientAccount(
        id=row.id,
        subject=row.subject,
        patient_identity_id=row.patient_identity_id,
        status=PatientAccountStatus(row.status),
        created_at=row.created_at,
    )
