from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clinical.infrastructure.models import (
    AdverseEventModel,
    AllergyModel,
    ClinicalNoteModel,
    ClinicalNoteWriteIdempotencyModel,
    ClinicalProvenanceModel,
    ConditionModel,
    ConsentModel,
    EncounterModel,
    EncounterParticipantModel,
    FamilyHistoryModel,
    ImmunizationModel,
    LaboratoryOrderModel,
    LaboratoryResultModel,
    LaboratorySpecimenModel,
    MedicalDeviceModel,
    MedicationModel,
    ObservationModel,
    ProcedureModel,
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

    async def add_note_write_idempotency(
        self, model: ClinicalNoteWriteIdempotencyModel
    ) -> ClinicalNoteWriteIdempotencyModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_note_write_idempotency(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        operation: str,
        idempotency_key: str,
    ) -> ClinicalNoteWriteIdempotencyModel | None:
        result = await self._session.execute(
            select(ClinicalNoteWriteIdempotencyModel).where(
                ClinicalNoteWriteIdempotencyModel.organization_id == organization_id,
                ClinicalNoteWriteIdempotencyModel.actor_id == actor_id,
                ClinicalNoteWriteIdempotencyModel.operation == operation,
                ClinicalNoteWriteIdempotencyModel.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def add_condition(self, model: ConditionModel) -> ConditionModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_observation(self, model: ObservationModel) -> ObservationModel:
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

    async def get_observation(self, observation_id: UUID) -> ObservationModel | None:
        return await self._session.get(ObservationModel, observation_id)

    async def get_observation_for_update(self, observation_id: UUID) -> ObservationModel | None:
        result = await self._session.execute(
            select(ObservationModel).where(ObservationModel.id == observation_id).with_for_update()
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

    async def list_observations_for_patient(
        self,
        patient_identity_id: UUID,
        organization_id: UUID,
        *,
        encounter_id: UUID | None = None,
    ) -> list[ObservationModel]:
        query = select(ObservationModel).where(
            ObservationModel.patient_identity_id == patient_identity_id,
            ObservationModel.organization_id == organization_id,
        )
        if encounter_id is not None:
            query = query.where(ObservationModel.encounter_id == encounter_id)
        result = await self._session.execute(
            query.order_by(ObservationModel.recorded_at.desc()).limit(100)
        )
        return list(result.scalars().all())

    async def add_lab_order(self, model: LaboratoryOrderModel) -> LaboratoryOrderModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_lab_specimen(self, model: LaboratorySpecimenModel) -> LaboratorySpecimenModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_lab_result(self, model: LaboratoryResultModel) -> LaboratoryResultModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_lab_order(self, order_id: UUID) -> LaboratoryOrderModel | None:
        return await self._session.get(LaboratoryOrderModel, order_id)

    async def get_lab_order_for_update(self, order_id: UUID) -> LaboratoryOrderModel | None:
        result = await self._session.execute(
            select(LaboratoryOrderModel)
            .where(LaboratoryOrderModel.id == order_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_lab_specimen(self, specimen_id: UUID) -> LaboratorySpecimenModel | None:
        return await self._session.get(LaboratorySpecimenModel, specimen_id)

    async def get_lab_specimen_for_update(
        self, specimen_id: UUID
    ) -> LaboratorySpecimenModel | None:
        result = await self._session.execute(
            select(LaboratorySpecimenModel)
            .where(LaboratorySpecimenModel.id == specimen_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_lab_result(self, result_id: UUID) -> LaboratoryResultModel | None:
        return await self._session.get(LaboratoryResultModel, result_id)

    async def get_lab_result_for_update(self, result_id: UUID) -> LaboratoryResultModel | None:
        result = await self._session.execute(
            select(LaboratoryResultModel)
            .where(LaboratoryResultModel.id == result_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_lab_orders_for_patient(
        self, patient_identity_id: UUID, organization_id: UUID
    ) -> list[LaboratoryOrderModel]:
        result = await self._session.execute(
            select(LaboratoryOrderModel)
            .where(
                LaboratoryOrderModel.patient_identity_id == patient_identity_id,
                LaboratoryOrderModel.organization_id == organization_id,
            )
            .order_by(LaboratoryOrderModel.ordered_at.desc())
            .limit(100)
        )
        return list(result.scalars().all())

    async def list_lab_specimens_for_patient(
        self, patient_identity_id: UUID, organization_id: UUID
    ) -> list[LaboratorySpecimenModel]:
        result = await self._session.execute(
            select(LaboratorySpecimenModel)
            .where(
                LaboratorySpecimenModel.patient_identity_id == patient_identity_id,
                LaboratorySpecimenModel.organization_id == organization_id,
            )
            .order_by(LaboratorySpecimenModel.collected_at.desc())
            .limit(100)
        )
        return list(result.scalars().all())

    async def list_lab_results_for_patient(
        self, patient_identity_id: UUID, organization_id: UUID
    ) -> list[LaboratoryResultModel]:
        result = await self._session.execute(
            select(LaboratoryResultModel)
            .where(
                LaboratoryResultModel.patient_identity_id == patient_identity_id,
                LaboratoryResultModel.organization_id == organization_id,
            )
            .order_by(LaboratoryResultModel.recorded_at.desc())
            .limit(100)
        )
        return list(result.scalars().all())

    async def add_medication(self, model: MedicationModel) -> MedicationModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_medication(self, medication_id: UUID) -> MedicationModel | None:
        return await self._session.get(MedicationModel, medication_id)

    async def get_medication_for_update(self, medication_id: UUID) -> MedicationModel | None:
        result = await self._session.execute(
            select(MedicationModel).where(MedicationModel.id == medication_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_medications_for_patient(
        self,
        patient_identity_id: UUID,
        organization_id: UUID,
        *,
        encounter_id: UUID | None = None,
    ) -> list[MedicationModel]:
        query = select(MedicationModel).where(
            MedicationModel.patient_identity_id == patient_identity_id,
            MedicationModel.organization_id == organization_id,
        )
        if encounter_id is not None:
            query = query.where(MedicationModel.encounter_id == encounter_id)
        result = await self._session.execute(
            query.order_by(MedicationModel.recorded_at.desc()).limit(100)
        )
        return list(result.scalars().all())

    async def add_allergy(self, model: AllergyModel) -> AllergyModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_allergy(self, allergy_id: UUID) -> AllergyModel | None:
        return await self._session.get(AllergyModel, allergy_id)

    async def get_allergy_for_update(self, allergy_id: UUID) -> AllergyModel | None:
        result = await self._session.execute(
            select(AllergyModel).where(AllergyModel.id == allergy_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_allergies_for_patient(
        self,
        patient_identity_id: UUID,
        organization_id: UUID,
        *,
        encounter_id: UUID | None = None,
    ) -> list[AllergyModel]:
        query = select(AllergyModel).where(
            AllergyModel.patient_identity_id == patient_identity_id,
            AllergyModel.organization_id == organization_id,
        )
        if encounter_id is not None:
            query = query.where(AllergyModel.encounter_id == encounter_id)
        result = await self._session.execute(
            query.order_by(AllergyModel.recorded_at.desc()).limit(100)
        )
        return list(result.scalars().all())

    async def add_consent(self, model: ConsentModel) -> ConsentModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_consent(self, consent_id: UUID) -> ConsentModel | None:
        return await self._session.get(ConsentModel, consent_id)

    async def get_consent_for_update(self, consent_id: UUID) -> ConsentModel | None:
        result = await self._session.execute(
            select(ConsentModel).where(ConsentModel.id == consent_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_consents_for_patient(
        self,
        patient_identity_id: UUID,
        organization_id: UUID,
        *,
        encounter_id: UUID | None = None,
    ) -> list[ConsentModel]:
        query = select(ConsentModel).where(
            ConsentModel.patient_identity_id == patient_identity_id,
            ConsentModel.organization_id == organization_id,
        )
        if encounter_id is not None:
            query = query.where(ConsentModel.encounter_id == encounter_id)
        result = await self._session.execute(
            query.order_by(ConsentModel.recorded_at.desc()).limit(100)
        )
        return list(result.scalars().all())

    async def add_immunization(self, model: ImmunizationModel) -> ImmunizationModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_immunization(self, immunization_id: UUID) -> ImmunizationModel | None:
        return await self._session.get(ImmunizationModel, immunization_id)

    async def get_immunization_for_update(self, immunization_id: UUID) -> ImmunizationModel | None:
        result = await self._session.execute(
            select(ImmunizationModel)
            .where(ImmunizationModel.id == immunization_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_immunizations_for_patient(
        self,
        patient_identity_id: UUID,
        organization_id: UUID,
        *,
        encounter_id: UUID | None = None,
    ) -> list[ImmunizationModel]:
        query = select(ImmunizationModel).where(
            ImmunizationModel.patient_identity_id == patient_identity_id,
            ImmunizationModel.organization_id == organization_id,
        )
        if encounter_id is not None:
            query = query.where(ImmunizationModel.encounter_id == encounter_id)
        result = await self._session.execute(
            query.order_by(ImmunizationModel.recorded_at.desc()).limit(100)
        )
        return list(result.scalars().all())

    async def add_procedure(self, model: ProcedureModel) -> ProcedureModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_procedure(self, procedure_id: UUID) -> ProcedureModel | None:
        return await self._session.get(ProcedureModel, procedure_id)

    async def get_procedure_for_update(self, procedure_id: UUID) -> ProcedureModel | None:
        result = await self._session.execute(
            select(ProcedureModel).where(ProcedureModel.id == procedure_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_procedures_for_patient(
        self,
        patient_identity_id: UUID,
        organization_id: UUID,
        *,
        encounter_id: UUID | None = None,
    ) -> list[ProcedureModel]:
        query = select(ProcedureModel).where(
            ProcedureModel.patient_identity_id == patient_identity_id,
            ProcedureModel.organization_id == organization_id,
        )
        if encounter_id is not None:
            query = query.where(ProcedureModel.encounter_id == encounter_id)
        result = await self._session.execute(
            query.order_by(ProcedureModel.recorded_at.desc()).limit(100)
        )
        return list(result.scalars().all())

    async def add_medical_device(self, model: MedicalDeviceModel) -> MedicalDeviceModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_medical_device(self, medical_device_id: UUID) -> MedicalDeviceModel | None:
        return await self._session.get(MedicalDeviceModel, medical_device_id)

    async def get_medical_device_for_update(
        self, medical_device_id: UUID
    ) -> MedicalDeviceModel | None:
        result = await self._session.execute(
            select(MedicalDeviceModel)
            .where(MedicalDeviceModel.id == medical_device_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_medical_devices_for_patient(
        self,
        patient_identity_id: UUID,
        organization_id: UUID,
        *,
        encounter_id: UUID | None = None,
    ) -> list[MedicalDeviceModel]:
        query = select(MedicalDeviceModel).where(
            MedicalDeviceModel.patient_identity_id == patient_identity_id,
            MedicalDeviceModel.organization_id == organization_id,
        )
        if encounter_id is not None:
            query = query.where(MedicalDeviceModel.encounter_id == encounter_id)
        result = await self._session.execute(
            query.order_by(MedicalDeviceModel.recorded_at.desc()).limit(100)
        )
        return list(result.scalars().all())

    async def add_adverse_event(self, model: AdverseEventModel) -> AdverseEventModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_adverse_event(self, adverse_event_id: UUID) -> AdverseEventModel | None:
        return await self._session.get(AdverseEventModel, adverse_event_id)

    async def get_adverse_event_for_update(
        self, adverse_event_id: UUID
    ) -> AdverseEventModel | None:
        result = await self._session.execute(
            select(AdverseEventModel)
            .where(AdverseEventModel.id == adverse_event_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_adverse_events_for_patient(
        self,
        patient_identity_id: UUID,
        organization_id: UUID,
        *,
        encounter_id: UUID | None = None,
    ) -> list[AdverseEventModel]:
        query = select(AdverseEventModel).where(
            AdverseEventModel.patient_identity_id == patient_identity_id,
            AdverseEventModel.organization_id == organization_id,
        )
        if encounter_id is not None:
            query = query.where(AdverseEventModel.encounter_id == encounter_id)
        result = await self._session.execute(
            query.order_by(AdverseEventModel.recorded_at.desc()).limit(100)
        )
        return list(result.scalars().all())

    async def add_family_history(self, model: FamilyHistoryModel) -> FamilyHistoryModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_family_history(self, family_history_id: UUID) -> FamilyHistoryModel | None:
        return await self._session.get(FamilyHistoryModel, family_history_id)

    async def get_family_history_for_update(
        self, family_history_id: UUID
    ) -> FamilyHistoryModel | None:
        result = await self._session.execute(
            select(FamilyHistoryModel)
            .where(FamilyHistoryModel.id == family_history_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_family_histories_for_patient(
        self,
        patient_identity_id: UUID,
        organization_id: UUID,
        *,
        encounter_id: UUID | None = None,
    ) -> list[FamilyHistoryModel]:
        query = select(FamilyHistoryModel).where(
            FamilyHistoryModel.patient_identity_id == patient_identity_id,
            FamilyHistoryModel.organization_id == organization_id,
        )
        if encounter_id is not None:
            query = query.where(FamilyHistoryModel.encounter_id == encounter_id)
        result = await self._session.execute(
            query.order_by(FamilyHistoryModel.recorded_at.desc()).limit(100)
        )
        return list(result.scalars().all())
