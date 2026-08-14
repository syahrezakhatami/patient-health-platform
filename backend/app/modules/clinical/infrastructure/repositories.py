from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clinical.infrastructure.models import (
    ClinicalNoteModel,
    ClinicalProvenanceModel,
    ConditionModel,
    EncounterModel,
    EncounterParticipantModel,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class ClinicalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_encounter(self, model: EncounterModel) -> EncounterModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_participant(self, model: EncounterParticipantModel) -> EncounterParticipantModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_note(self, model: ClinicalNoteModel) -> ClinicalNoteModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_condition(self, model: ConditionModel) -> ConditionModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_provenance(self, model: ClinicalProvenanceModel) -> ClinicalProvenanceModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_encounter(self, encounter_id: UUID) -> EncounterModel | None:
        return await self._session.get(EncounterModel, encounter_id)

    async def get_encounter_for_update(self, encounter_id: UUID) -> EncounterModel | None:
        result = await self._session.execute(
            select(EncounterModel).where(EncounterModel.id == encounter_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_note(self, note_id: UUID) -> ClinicalNoteModel | None:
        return await self._session.get(ClinicalNoteModel, note_id)

    async def get_note_for_update(self, note_id: UUID) -> ClinicalNoteModel | None:
        result = await self._session.execute(
            select(ClinicalNoteModel).where(ClinicalNoteModel.id == note_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_condition(self, condition_id: UUID) -> ConditionModel | None:
        return await self._session.get(ConditionModel, condition_id)

    async def get_condition_for_update(self, condition_id: UUID) -> ConditionModel | None:
        result = await self._session.execute(
            select(ConditionModel).where(ConditionModel.id == condition_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_encounters_for_patient(
        self, patient_identity_id: UUID, organization_id: UUID
    ) -> list[EncounterModel]:
        result = await self._session.execute(
            select(EncounterModel)
            .where(
                EncounterModel.patient_identity_id == patient_identity_id,
                EncounterModel.organization_id == organization_id,
            )
            .order_by(EncounterModel.started_at.desc())
            .limit(100)
        )
        return list(result.scalars().all())

    async def list_notes_for_encounter(
        self, encounter_id: UUID, organization_id: UUID
    ) -> list[ClinicalNoteModel]:
        result = await self._session.execute(
            select(ClinicalNoteModel)
            .where(
                ClinicalNoteModel.encounter_id == encounter_id,
                ClinicalNoteModel.organization_id == organization_id,
            )
            .order_by(ClinicalNoteModel.authored_at.desc())
            .limit(100)
        )
        return list(result.scalars().all())

    async def list_conditions_for_patient(
        self,
        patient_identity_id: UUID,
        organization_id: UUID,
        *,
        encounter_id: UUID | None = None,
    ) -> list[ConditionModel]:
        query = select(ConditionModel).where(
            ConditionModel.patient_identity_id == patient_identity_id,
            ConditionModel.organization_id == organization_id,
        )
        if encounter_id is not None:
            query = query.where(ConditionModel.encounter_id == encounter_id)
        result = await self._session.execute(
            query.order_by(ConditionModel.recorded_at.desc()).limit(100)
        )
        return list(result.scalars().all())
