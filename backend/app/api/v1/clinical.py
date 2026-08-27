from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import (
    CorrelationId,
    CurrentAudit,
    CurrentPrincipal,
    RequestFacilityId,
    RequestOrganizationId,
    RequestPurpose,
    RequiredIdempotencyKey,
    require_staff_audience,
)
from app.api.v1.schemas import (
    AdverseEventResponse,
    AllergyResponse,
    AmendAdverseEventRequest,
    AmendAllergyRequest,
    AmendConsentRequest,
    AmendFamilyHistoryRequest,
    AmendImmunizationRequest,
    AmendLaboratoryResultRequest,
    AmendMedicalDeviceRequest,
    AmendObservationRequest,
    AmendProcedureRequest,
    ChangeConditionStatusRequest,
    ChangeEncounterStatusRequest,
    ClinicalNoteResponse,
    CodeableConceptRequest,
    ConditionResponse,
    ConsentResponse,
    CreateAdverseEventRequest,
    CreateAllergyRequest,
    CreateClinicalNoteRequest,
    CreateConditionRequest,
    CreateConsentRequest,
    CreateEncounterRequest,
    CreateFamilyHistoryRequest,
    CreateImmunizationRequest,
    CreateLaboratoryOrderRequest,
    CreateLaboratoryResultRequest,
    CreateLaboratorySpecimenRequest,
    CreateMedicalDeviceRequest,
    CreateMedicationRequest,
    CreateObservationRequest,
    CreateProcedureRequest,
    EncounterResponse,
    FamilyHistoryResponse,
    FinalizeClinicalNoteRequest,
    ImmunizationResponse,
    LaboratoryOrderResponse,
    LaboratoryResultResponse,
    LaboratorySpecimenResponse,
    MedicalDeviceResponse,
    MedicationResponse,
    ObservationResponse,
    ProcedureResponse,
    UpdateClinicalNoteRequest,
)
from app.core.dependencies import CurrentPDP, DbSession
from app.core.errors import AppError
from app.modules.clinical.application.services import (
    AdverseEventView,
    AllergyView,
    ClinicalNoteView,
    ClinicalService,
    ConditionView,
    ConsentView,
    EncounterView,
    FamilyHistoryView,
    ImmunizationView,
    LaboratoryOrderView,
    LaboratoryResultView,
    LaboratorySpecimenView,
    MedicalDeviceView,
    MedicationView,
    ObservationView,
    ProcedureView,
)
from app.modules.clinical.domain.laboratory_values import (
    LaboratoryResultValue,
    parse_laboratory_result_value,
)
from app.modules.clinical.domain.observation_values import ObservationValue, parse_observation_value
from app.modules.clinical.domain.terminology import CodeableConcept, parse_codeable_concept

router = APIRouter(
    prefix="/clinical",
    tags=["clinical"],
    dependencies=[Depends(require_staff_audience)],
)


def _service(session: DbSession, pdp: CurrentPDP, audit: CurrentAudit) -> ClinicalService:
    return ClinicalService(session, pdp, audit)


def _encounter_response(view: EncounterView) -> EncounterResponse:
    return EncounterResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        encounter_class=view.encounter_class,
        status=view.status,
        display_label=view.display_label,
        started_at=view.started_at,
        ended_at=view.ended_at,
        reason=None
        if view.reason is None
        else CodeableConceptRequest(
            system=view.reason.system,
            code=view.reason.code,
            display=view.reason.display,
        ),
    )


def _note_response(view: ClinicalNoteView) -> ClinicalNoteResponse:
    return ClinicalNoteResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        note_type=view.note_type,
        body_text=view.body_text,
        record_status=view.record_status,
        version=view.version,
        authored_at=view.authored_at,
        finalized_at=view.finalized_at,
    )


def _condition_response(view: ConditionView) -> ConditionResponse:
    return ConditionResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        category=view.category,
        code=CodeableConceptRequest(
            system=view.code.system,
            code=view.code.code,
            display=view.code.display,
        ),
        clinical_status=view.clinical_status,
        verification_status=view.verification_status,
        onset_at=view.onset_at,
        abatement_at=view.abatement_at,
        recorded_at=view.recorded_at,
    )


def _observation_response(view: ObservationView) -> ObservationResponse:
    return ObservationResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        category=view.category,
        code=CodeableConceptRequest(
            system=view.code.system,
            code=view.code.code,
            display=view.code.display,
        ),
        status=view.status,
        value_type=view.value_type,
        value_numeric=view.value_numeric,
        value_text=view.value_text,
        value_boolean=view.value_boolean,
        value_coded=None
        if view.value_coded is None
        else CodeableConceptRequest(
            system=view.value_coded.system,
            code=view.value_coded.code,
            display=view.value_coded.display,
        ),
        unit=view.unit,
        reference_range_low=view.reference_range_low,
        reference_range_high=view.reference_range_high,
        effective_at=view.effective_at,
        recorded_at=view.recorded_at,
        version=view.version,
    )


def _parse_observation_value_body(
    body: CreateObservationRequest | AmendObservationRequest,
) -> ObservationValue:
    return parse_observation_value(
        value_type=body.value_type,
        value_numeric=body.value_numeric,
        value_text=body.value_text,
        value_boolean=body.value_boolean,
        value_coded=None if body.value_coded is None else body.value_coded.model_dump(),
        unit=body.unit,
        range_low=body.reference_range_low,
        range_high=body.reference_range_high,
    )


@router.post("/encounters", response_model=EncounterResponse)
async def create_encounter(
    body: CreateEncounterRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> EncounterResponse:
    view = await _service(session, pdp, audit).create_encounter(
        principal,
        patient_identity_id=body.patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        encounter_class=body.encounter_class,
        started_at=body.started_at,
        reason=parse_codeable_concept(None if body.reason is None else body.reason.model_dump()),
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _encounter_response(view)


@router.get("/encounters", response_model=list[EncounterResponse])
async def list_encounters(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
) -> list[EncounterResponse]:
    views = await _service(session, pdp, audit).list_encounters(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_encounter_response(item) for item in views]


@router.get("/encounters/{encounter_id}", response_model=EncounterResponse)
async def get_encounter(
    encounter_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> EncounterResponse:
    view = await _service(session, pdp, audit).get_encounter(
        principal,
        encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _encounter_response(view)


@router.post("/encounters/{encounter_id}/status", response_model=EncounterResponse)
async def change_encounter_status(
    encounter_id: UUID,
    body: ChangeEncounterStatusRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> EncounterResponse:
    view = await _service(session, pdp, audit).change_encounter_status(
        principal,
        encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        status=body.status,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _encounter_response(view)


@router.post("/notes", response_model=ClinicalNoteResponse)
async def create_note(
    body: CreateClinicalNoteRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    idempotency_key: RequiredIdempotencyKey,
) -> ClinicalNoteResponse:
    view = await _service(session, pdp, audit).create_note(
        principal,
        expected_patient_identity_id=body.expected_patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        note_type=body.note_type,
        body_text=body.body_text,
        purpose=purpose,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return _note_response(view)


@router.get("/notes/{note_id}", response_model=ClinicalNoteResponse)
async def get_note(
    note_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ClinicalNoteResponse:
    view = await _service(session, pdp, audit).get_note(
        principal,
        note_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _note_response(view)


@router.post("/notes/{note_id}", response_model=ClinicalNoteResponse)
async def update_draft_note(
    note_id: UUID,
    body: UpdateClinicalNoteRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ClinicalNoteResponse:
    view = await _service(session, pdp, audit).update_draft_note(
        principal,
        note_id,
        expected_patient_identity_id=body.expected_patient_identity_id,
        expected_version=body.expected_version,
        organization_id=organization_id,
        facility_id=facility_id,
        body_text=body.body_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _note_response(view)


@router.post("/notes/{note_id}/finalize", response_model=ClinicalNoteResponse)
async def finalize_note(
    note_id: UUID,
    body: FinalizeClinicalNoteRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    idempotency_key: RequiredIdempotencyKey,
) -> ClinicalNoteResponse:
    view = await _service(session, pdp, audit).finalize_note(
        principal,
        note_id,
        expected_patient_identity_id=body.expected_patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return _note_response(view)


@router.post("/notes/{note_id}/entered-in-error", response_model=ClinicalNoteResponse)
async def mark_note_entered_in_error(
    note_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ClinicalNoteResponse:
    view = await _service(session, pdp, audit).mark_note_entered_in_error(
        principal,
        note_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _note_response(view)


@router.post("/conditions", response_model=ConditionResponse)
async def create_condition(
    body: CreateConditionRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ConditionResponse:
    code = parse_codeable_concept(body.code.model_dump())
    if code is None:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    view = await _service(session, pdp, audit).create_condition(
        principal,
        patient_identity_id=body.patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        category=body.category,
        code=code,
        clinical_status=body.clinical_status,
        verification_status=body.verification_status,
        onset_at=body.onset_at,
        abatement_at=body.abatement_at,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _condition_response(view)


@router.get("/conditions", response_model=list[ConditionResponse])
async def list_conditions(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
    encounter_id: Annotated[UUID | None, Query()] = None,
) -> list[ConditionResponse]:
    views = await _service(session, pdp, audit).list_conditions(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        encounter_id=encounter_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_condition_response(item) for item in views]


@router.get("/conditions/{condition_id}", response_model=ConditionResponse)
async def get_condition(
    condition_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ConditionResponse:
    view = await _service(session, pdp, audit).get_condition(
        principal,
        condition_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _condition_response(view)


@router.post("/conditions/{condition_id}/status", response_model=ConditionResponse)
async def change_condition_status(
    condition_id: UUID,
    body: ChangeConditionStatusRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ConditionResponse:
    view = await _service(session, pdp, audit).change_condition_status(
        principal,
        condition_id,
        organization_id=organization_id,
        facility_id=facility_id,
        clinical_status=body.clinical_status,
        verification_status=body.verification_status,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _condition_response(view)


@router.post("/conditions/{condition_id}/entered-in-error", response_model=ConditionResponse)
async def mark_condition_entered_in_error(
    condition_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ConditionResponse:
    view = await _service(session, pdp, audit).mark_condition_entered_in_error(
        principal,
        condition_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _condition_response(view)


@router.post("/observations", response_model=ObservationResponse)
async def create_observation(
    body: CreateObservationRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ObservationResponse:
    code = parse_codeable_concept(body.code.model_dump())
    if code is None:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    view = await _service(session, pdp, audit).create_observation(
        principal,
        patient_identity_id=body.patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        category=body.category,
        code=code,
        value=_parse_observation_value_body(body),
        effective_at=body.effective_at,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _observation_response(view)


@router.get("/observations", response_model=list[ObservationResponse])
async def list_observations(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
    encounter_id: Annotated[UUID | None, Query()] = None,
) -> list[ObservationResponse]:
    views = await _service(session, pdp, audit).list_observations(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        encounter_id=encounter_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_observation_response(item) for item in views]


@router.get("/observations/{observation_id}", response_model=ObservationResponse)
async def get_observation(
    observation_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ObservationResponse:
    view = await _service(session, pdp, audit).get_observation(
        principal,
        observation_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _observation_response(view)


@router.post("/observations/{observation_id}/amend", response_model=ObservationResponse)
async def amend_observation(
    observation_id: UUID,
    body: AmendObservationRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ObservationResponse:
    view = await _service(session, pdp, audit).amend_observation(
        principal,
        observation_id,
        organization_id=organization_id,
        facility_id=facility_id,
        value=_parse_observation_value_body(body),
        effective_at=body.effective_at,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _observation_response(view)


@router.post("/observations/{observation_id}/entered-in-error", response_model=ObservationResponse)
async def mark_observation_entered_in_error(
    observation_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ObservationResponse:
    view = await _service(session, pdp, audit).mark_observation_entered_in_error(
        principal,
        observation_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _observation_response(view)


def _codeable(concept: CodeableConcept) -> CodeableConceptRequest:
    return CodeableConceptRequest(
        system=concept.system,
        code=concept.code,
        display=concept.display,
    )


def _lab_order_response(view: LaboratoryOrderView) -> LaboratoryOrderResponse:
    return LaboratoryOrderResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        code=_codeable(view.code),
        status=view.status,
        ordered_at=view.ordered_at,
        version=view.version,
    )


def _lab_specimen_response(view: LaboratorySpecimenView) -> LaboratorySpecimenResponse:
    return LaboratorySpecimenResponse(
        id=view.id,
        laboratory_order_id=view.laboratory_order_id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        specimen_type=view.specimen_type,
        status=view.status,
        collected_at=view.collected_at,
    )


def _lab_result_response(view: LaboratoryResultView) -> LaboratoryResultResponse:
    return LaboratoryResultResponse(
        id=view.id,
        laboratory_order_id=view.laboratory_order_id,
        laboratory_specimen_id=view.laboratory_specimen_id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        code=_codeable(view.code),
        status=view.status,
        value_type=view.value_type,
        value_numeric=view.value_numeric,
        value_text=view.value_text,
        value_boolean=view.value_boolean,
        value_coded=None if view.value_coded is None else _codeable(view.value_coded),
        unit=view.unit,
        reference_range_low=view.reference_range_low,
        reference_range_high=view.reference_range_high,
        interpretation=view.interpretation,
        effective_at=view.effective_at,
        recorded_at=view.recorded_at,
        version=view.version,
    )


def _parse_lab_result_value_body(
    body: CreateLaboratoryResultRequest | AmendLaboratoryResultRequest,
) -> LaboratoryResultValue:
    return parse_laboratory_result_value(
        value_type=body.value_type,
        value_numeric=body.value_numeric,
        value_text=body.value_text,
        value_boolean=body.value_boolean,
        value_coded=None if body.value_coded is None else body.value_coded.model_dump(),
        unit=body.unit,
        range_low=body.reference_range_low,
        range_high=body.reference_range_high,
    )


@router.post("/laboratory/orders", response_model=LaboratoryOrderResponse)
async def create_lab_order(
    body: CreateLaboratoryOrderRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratoryOrderResponse:
    code = parse_codeable_concept(body.code.model_dump())
    if code is None:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    view = await _service(session, pdp, audit).create_lab_order(
        principal,
        patient_identity_id=body.patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        code=code,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_order_response(view)


@router.get("/laboratory/orders", response_model=list[LaboratoryOrderResponse])
async def list_lab_orders(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
) -> list[LaboratoryOrderResponse]:
    views = await _service(session, pdp, audit).list_lab_orders(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_lab_order_response(item) for item in views]


@router.get("/laboratory/orders/{order_id}", response_model=LaboratoryOrderResponse)
async def get_lab_order(
    order_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratoryOrderResponse:
    view = await _service(session, pdp, audit).get_lab_order(
        principal,
        order_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_order_response(view)


@router.post("/laboratory/orders/{order_id}/cancel", response_model=LaboratoryOrderResponse)
async def cancel_lab_order(
    order_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratoryOrderResponse:
    view = await _service(session, pdp, audit).cancel_lab_order(
        principal,
        order_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_order_response(view)


@router.post(
    "/laboratory/orders/{order_id}/entered-in-error",
    response_model=LaboratoryOrderResponse,
)
async def mark_lab_order_entered_in_error(
    order_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratoryOrderResponse:
    view = await _service(session, pdp, audit).mark_lab_order_entered_in_error(
        principal,
        order_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_order_response(view)


@router.post("/laboratory/specimens", response_model=LaboratorySpecimenResponse)
async def collect_lab_specimen(
    body: CreateLaboratorySpecimenRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratorySpecimenResponse:
    view = await _service(session, pdp, audit).collect_lab_specimen(
        principal,
        laboratory_order_id=body.laboratory_order_id,
        organization_id=organization_id,
        facility_id=facility_id,
        specimen_type=body.specimen_type,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_specimen_response(view)


@router.get("/laboratory/specimens", response_model=list[LaboratorySpecimenResponse])
async def list_lab_specimens(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
) -> list[LaboratorySpecimenResponse]:
    views = await _service(session, pdp, audit).list_lab_specimens(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_lab_specimen_response(item) for item in views]


@router.get("/laboratory/specimens/{specimen_id}", response_model=LaboratorySpecimenResponse)
async def get_lab_specimen(
    specimen_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratorySpecimenResponse:
    view = await _service(session, pdp, audit).get_lab_specimen(
        principal,
        specimen_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_specimen_response(view)


@router.post(
    "/laboratory/specimens/{specimen_id}/reject",
    response_model=LaboratorySpecimenResponse,
)
async def reject_lab_specimen(
    specimen_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratorySpecimenResponse:
    view = await _service(session, pdp, audit).reject_lab_specimen(
        principal,
        specimen_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_specimen_response(view)


@router.post(
    "/laboratory/specimens/{specimen_id}/entered-in-error",
    response_model=LaboratorySpecimenResponse,
)
async def mark_lab_specimen_entered_in_error(
    specimen_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratorySpecimenResponse:
    view = await _service(session, pdp, audit).mark_lab_specimen_entered_in_error(
        principal,
        specimen_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_specimen_response(view)


@router.post("/laboratory/results", response_model=LaboratoryResultResponse)
async def create_lab_result(
    body: CreateLaboratoryResultRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratoryResultResponse:
    code = parse_codeable_concept(body.code.model_dump())
    if code is None:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    view = await _service(session, pdp, audit).create_lab_result(
        principal,
        laboratory_specimen_id=body.laboratory_specimen_id,
        organization_id=organization_id,
        facility_id=facility_id,
        code=code,
        value=_parse_lab_result_value_body(body),
        interpretation=body.interpretation,
        effective_at=body.effective_at,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_result_response(view)


@router.get("/laboratory/results", response_model=list[LaboratoryResultResponse])
async def list_lab_results(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
) -> list[LaboratoryResultResponse]:
    views = await _service(session, pdp, audit).list_lab_results(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_lab_result_response(item) for item in views]


@router.get("/laboratory/results/{result_id}", response_model=LaboratoryResultResponse)
async def get_lab_result(
    result_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratoryResultResponse:
    view = await _service(session, pdp, audit).get_lab_result(
        principal,
        result_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_result_response(view)


@router.post(
    "/laboratory/results/{result_id}/amend",
    response_model=LaboratoryResultResponse,
)
async def amend_lab_result(
    result_id: UUID,
    body: AmendLaboratoryResultRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratoryResultResponse:
    view = await _service(session, pdp, audit).amend_lab_result(
        principal,
        result_id,
        organization_id=organization_id,
        facility_id=facility_id,
        value=_parse_lab_result_value_body(body),
        interpretation=body.interpretation,
        effective_at=body.effective_at,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_result_response(view)


@router.post(
    "/laboratory/results/{result_id}/entered-in-error",
    response_model=LaboratoryResultResponse,
)
async def mark_lab_result_entered_in_error(
    result_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> LaboratoryResultResponse:
    view = await _service(session, pdp, audit).mark_lab_result_entered_in_error(
        principal,
        result_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _lab_result_response(view)


def _medication_response(view: MedicationView) -> MedicationResponse:
    return MedicationResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        category=view.category,
        code=_codeable(view.code),
        status=view.status,
        dose_numeric=view.dose_numeric,
        dose_unit=view.dose_unit,
        route=view.route,
        started_at=view.started_at,
        stopped_at=view.stopped_at,
        recorded_at=view.recorded_at,
        version=view.version,
    )


@router.post("/medications", response_model=MedicationResponse)
async def create_medication(
    body: CreateMedicationRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> MedicationResponse:
    code = parse_codeable_concept(body.code.model_dump())
    if code is None:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    view = await _service(session, pdp, audit).create_medication(
        principal,
        patient_identity_id=body.patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        category=body.category,
        code=code,
        dose_numeric=body.dose_numeric,
        dose_unit=body.dose_unit,
        route=body.route,
        started_at=body.started_at,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _medication_response(view)


@router.get("/medications", response_model=list[MedicationResponse])
async def list_medications(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
    encounter_id: Annotated[UUID | None, Query()] = None,
) -> list[MedicationResponse]:
    views = await _service(session, pdp, audit).list_medications(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        encounter_id=encounter_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_medication_response(item) for item in views]


@router.get("/medications/{medication_id}", response_model=MedicationResponse)
async def get_medication(
    medication_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> MedicationResponse:
    view = await _service(session, pdp, audit).get_medication(
        principal,
        medication_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _medication_response(view)


@router.post("/medications/{medication_id}/stop", response_model=MedicationResponse)
async def stop_medication(
    medication_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> MedicationResponse:
    view = await _service(session, pdp, audit).stop_medication(
        principal,
        medication_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _medication_response(view)


@router.post("/medications/{medication_id}/entered-in-error", response_model=MedicationResponse)
async def mark_medication_entered_in_error(
    medication_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> MedicationResponse:
    view = await _service(session, pdp, audit).mark_medication_entered_in_error(
        principal,
        medication_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _medication_response(view)


def _allergy_response(view: AllergyView) -> AllergyResponse:
    return AllergyResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        category=view.category,
        code=_codeable(view.code),
        status=view.status,
        clinical_status=view.clinical_status,
        verification_status=view.verification_status,
        criticality=view.criticality,
        severity=view.severity,
        reaction=None if view.reaction is None else _codeable(view.reaction),
        onset_at=view.onset_at,
        recorded_at=view.recorded_at,
        version=view.version,
    )


@router.post("/allergies", response_model=AllergyResponse)
async def create_allergy(
    body: CreateAllergyRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> AllergyResponse:
    code = parse_codeable_concept(body.code.model_dump())
    if code is None:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    reaction = None
    if body.reaction is not None:
        reaction = parse_codeable_concept(body.reaction.model_dump())
        if reaction is None:
            raise AppError(
                "invalid_codeable_concept",
                "Codeable concept requires system and code",
                status_code=422,
            )
    view = await _service(session, pdp, audit).create_allergy(
        principal,
        patient_identity_id=body.patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        category=body.category,
        code=code,
        clinical_status=body.clinical_status,
        verification_status=body.verification_status,
        criticality=body.criticality,
        severity=body.severity,
        reaction=reaction,
        onset_at=body.onset_at,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _allergy_response(view)


@router.get("/allergies", response_model=list[AllergyResponse])
async def list_allergies(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
    encounter_id: Annotated[UUID | None, Query()] = None,
) -> list[AllergyResponse]:
    views = await _service(session, pdp, audit).list_allergies(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        encounter_id=encounter_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_allergy_response(item) for item in views]


@router.get("/allergies/{allergy_id}", response_model=AllergyResponse)
async def get_allergy(
    allergy_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> AllergyResponse:
    view = await _service(session, pdp, audit).get_allergy(
        principal,
        allergy_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _allergy_response(view)


@router.post("/allergies/{allergy_id}/amend", response_model=AllergyResponse)
async def amend_allergy(
    allergy_id: UUID,
    body: AmendAllergyRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> AllergyResponse:
    reaction = None
    if body.reaction is not None:
        reaction = parse_codeable_concept(body.reaction.model_dump())
        if reaction is None:
            raise AppError(
                "invalid_codeable_concept",
                "Codeable concept requires system and code",
                status_code=422,
            )
    view = await _service(session, pdp, audit).amend_allergy(
        principal,
        allergy_id,
        organization_id=organization_id,
        facility_id=facility_id,
        clinical_status=body.clinical_status,
        verification_status=body.verification_status,
        criticality=body.criticality,
        severity=body.severity,
        reaction=reaction,
        onset_at=body.onset_at,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _allergy_response(view)


@router.post("/allergies/{allergy_id}/entered-in-error", response_model=AllergyResponse)
async def mark_allergy_entered_in_error(
    allergy_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> AllergyResponse:
    view = await _service(session, pdp, audit).mark_allergy_entered_in_error(
        principal,
        allergy_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _allergy_response(view)


def _consent_response(view: ConsentView) -> ConsentResponse:
    return ConsentResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        category=view.category,
        scope=view.scope,
        decision=view.decision,
        code=None if view.code is None else _codeable(view.code),
        source=view.source,
        period_start=view.period_start,
        period_end=view.period_end,
        note_text=view.note_text,
        status=view.status,
        recorded_at=view.recorded_at,
        revoked_at=view.revoked_at,
        version=view.version,
        is_effective=view.is_effective,
    )


@router.post("/consents", response_model=ConsentResponse)
async def create_consent(
    body: CreateConsentRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ConsentResponse:
    code = None
    if body.code is not None:
        code = parse_codeable_concept(body.code.model_dump())
        if code is None:
            raise AppError(
                "invalid_codeable_concept",
                "Codeable concept requires system and code",
                status_code=422,
            )
    view = await _service(session, pdp, audit).create_consent(
        principal,
        patient_identity_id=body.patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        category=body.category,
        scope=body.scope,
        decision=body.decision,
        code=code,
        source=body.source,
        period_start=body.period_start,
        period_end=body.period_end,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _consent_response(view)


@router.get("/consents", response_model=list[ConsentResponse])
async def list_consents(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
    encounter_id: Annotated[UUID | None, Query()] = None,
) -> list[ConsentResponse]:
    views = await _service(session, pdp, audit).list_consents(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        encounter_id=encounter_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_consent_response(item) for item in views]


@router.get("/consents/{consent_id}", response_model=ConsentResponse)
async def get_consent(
    consent_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ConsentResponse:
    view = await _service(session, pdp, audit).get_consent(
        principal,
        consent_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _consent_response(view)


@router.post("/consents/{consent_id}/amend", response_model=ConsentResponse)
async def amend_consent(
    consent_id: UUID,
    body: AmendConsentRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ConsentResponse:
    view = await _service(session, pdp, audit).amend_consent(
        principal,
        consent_id,
        organization_id=organization_id,
        facility_id=facility_id,
        period_start=body.period_start,
        period_end=body.period_end,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _consent_response(view)


@router.post("/consents/{consent_id}/revoke", response_model=ConsentResponse)
async def revoke_consent(
    consent_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ConsentResponse:
    view = await _service(session, pdp, audit).revoke_consent(
        principal,
        consent_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _consent_response(view)


@router.post("/consents/{consent_id}/entered-in-error", response_model=ConsentResponse)
async def mark_consent_entered_in_error(
    consent_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ConsentResponse:
    view = await _service(session, pdp, audit).mark_consent_entered_in_error(
        principal,
        consent_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _consent_response(view)


def _immunization_response(view: ImmunizationView) -> ImmunizationResponse:
    return ImmunizationResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        category=view.category,
        code=_codeable(view.code),
        occurrence_at=view.occurrence_at,
        route=view.route,
        site=view.site,
        note_text=view.note_text,
        status=view.status,
        recorded_at=view.recorded_at,
        version=view.version,
    )


@router.post("/immunizations", response_model=ImmunizationResponse)
async def create_immunization(
    body: CreateImmunizationRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ImmunizationResponse:
    code = parse_codeable_concept(body.code.model_dump())
    if code is None:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    view = await _service(session, pdp, audit).create_immunization(
        principal,
        patient_identity_id=body.patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        category=body.category,
        code=code,
        occurrence_at=body.occurrence_at,
        route=body.route,
        site=body.site,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _immunization_response(view)


@router.get("/immunizations", response_model=list[ImmunizationResponse])
async def list_immunizations(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
    encounter_id: Annotated[UUID | None, Query()] = None,
) -> list[ImmunizationResponse]:
    views = await _service(session, pdp, audit).list_immunizations(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        encounter_id=encounter_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_immunization_response(item) for item in views]


@router.get("/immunizations/{immunization_id}", response_model=ImmunizationResponse)
async def get_immunization(
    immunization_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ImmunizationResponse:
    view = await _service(session, pdp, audit).get_immunization(
        principal,
        immunization_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _immunization_response(view)


@router.post("/immunizations/{immunization_id}/amend", response_model=ImmunizationResponse)
async def amend_immunization(
    immunization_id: UUID,
    body: AmendImmunizationRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ImmunizationResponse:
    view = await _service(session, pdp, audit).amend_immunization(
        principal,
        immunization_id,
        organization_id=organization_id,
        facility_id=facility_id,
        occurrence_at=body.occurrence_at,
        route=body.route,
        site=body.site,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _immunization_response(view)


@router.post(
    "/immunizations/{immunization_id}/entered-in-error",
    response_model=ImmunizationResponse,
)
async def mark_immunization_entered_in_error(
    immunization_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ImmunizationResponse:
    view = await _service(session, pdp, audit).mark_immunization_entered_in_error(
        principal,
        immunization_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _immunization_response(view)


def _procedure_response(view: ProcedureView) -> ProcedureResponse:
    return ProcedureResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        category=view.category,
        code=_codeable(view.code),
        occurrence_at=view.occurrence_at,
        note_text=view.note_text,
        status=view.status,
        recorded_at=view.recorded_at,
        version=view.version,
    )


@router.post("/procedures", response_model=ProcedureResponse)
async def create_procedure(
    body: CreateProcedureRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ProcedureResponse:
    code = parse_codeable_concept(body.code.model_dump())
    if code is None:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    view = await _service(session, pdp, audit).create_procedure(
        principal,
        patient_identity_id=body.patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        category=body.category,
        code=code,
        occurrence_at=body.occurrence_at,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _procedure_response(view)


@router.get("/procedures", response_model=list[ProcedureResponse])
async def list_procedures(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
    encounter_id: Annotated[UUID | None, Query()] = None,
) -> list[ProcedureResponse]:
    views = await _service(session, pdp, audit).list_procedures(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        encounter_id=encounter_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_procedure_response(item) for item in views]


@router.get("/procedures/{procedure_id}", response_model=ProcedureResponse)
async def get_procedure(
    procedure_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ProcedureResponse:
    view = await _service(session, pdp, audit).get_procedure(
        principal,
        procedure_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _procedure_response(view)


@router.post("/procedures/{procedure_id}/amend", response_model=ProcedureResponse)
async def amend_procedure(
    procedure_id: UUID,
    body: AmendProcedureRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ProcedureResponse:
    view = await _service(session, pdp, audit).amend_procedure(
        principal,
        procedure_id,
        organization_id=organization_id,
        facility_id=facility_id,
        occurrence_at=body.occurrence_at,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _procedure_response(view)


@router.post(
    "/procedures/{procedure_id}/entered-in-error",
    response_model=ProcedureResponse,
)
async def mark_procedure_entered_in_error(
    procedure_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ProcedureResponse:
    view = await _service(session, pdp, audit).mark_procedure_entered_in_error(
        principal,
        procedure_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _procedure_response(view)


def _medical_device_response(view: MedicalDeviceView) -> MedicalDeviceResponse:
    return MedicalDeviceResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        category=view.category,
        code=_codeable(view.code),
        association_status=view.association_status,
        occurrence_at=view.occurrence_at,
        note_text=view.note_text,
        status=view.status,
        recorded_at=view.recorded_at,
        version=view.version,
    )


@router.post("/medical-devices", response_model=MedicalDeviceResponse)
async def create_medical_device(
    body: CreateMedicalDeviceRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> MedicalDeviceResponse:
    code = parse_codeable_concept(body.code.model_dump())
    if code is None:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    view = await _service(session, pdp, audit).create_medical_device(
        principal,
        patient_identity_id=body.patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        category=body.category,
        code=code,
        association_status=body.association_status,
        occurrence_at=body.occurrence_at,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _medical_device_response(view)


@router.get("/medical-devices", response_model=list[MedicalDeviceResponse])
async def list_medical_devices(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
    encounter_id: Annotated[UUID | None, Query()] = None,
) -> list[MedicalDeviceResponse]:
    views = await _service(session, pdp, audit).list_medical_devices(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        encounter_id=encounter_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_medical_device_response(item) for item in views]


@router.get("/medical-devices/{medical_device_id}", response_model=MedicalDeviceResponse)
async def get_medical_device(
    medical_device_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> MedicalDeviceResponse:
    view = await _service(session, pdp, audit).get_medical_device(
        principal,
        medical_device_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _medical_device_response(view)


@router.post(
    "/medical-devices/{medical_device_id}/amend",
    response_model=MedicalDeviceResponse,
)
async def amend_medical_device(
    medical_device_id: UUID,
    body: AmendMedicalDeviceRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> MedicalDeviceResponse:
    view = await _service(session, pdp, audit).amend_medical_device(
        principal,
        medical_device_id,
        organization_id=organization_id,
        facility_id=facility_id,
        association_status=body.association_status,
        occurrence_at=body.occurrence_at,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _medical_device_response(view)


@router.post(
    "/medical-devices/{medical_device_id}/entered-in-error",
    response_model=MedicalDeviceResponse,
)
async def mark_medical_device_entered_in_error(
    medical_device_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> MedicalDeviceResponse:
    view = await _service(session, pdp, audit).mark_medical_device_entered_in_error(
        principal,
        medical_device_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _medical_device_response(view)


def _adverse_event_response(view: AdverseEventView) -> AdverseEventResponse:
    return AdverseEventResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        category=view.category,
        code=_codeable(view.code),
        severity=view.severity,
        medication_id=view.medication_id,
        medical_device_id=view.medical_device_id,
        procedure_id=view.procedure_id,
        occurrence_at=view.occurrence_at,
        note_text=view.note_text,
        status=view.status,
        recorded_at=view.recorded_at,
        version=view.version,
    )


@router.post("/adverse-events", response_model=AdverseEventResponse)
async def create_adverse_event(
    body: CreateAdverseEventRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> AdverseEventResponse:
    code = parse_codeable_concept(body.code.model_dump())
    if code is None:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    view = await _service(session, pdp, audit).create_adverse_event(
        principal,
        patient_identity_id=body.patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        category=body.category,
        code=code,
        severity=body.severity,
        medication_id=body.medication_id,
        medical_device_id=body.medical_device_id,
        procedure_id=body.procedure_id,
        occurrence_at=body.occurrence_at,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _adverse_event_response(view)


@router.get("/adverse-events", response_model=list[AdverseEventResponse])
async def list_adverse_events(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
    encounter_id: Annotated[UUID | None, Query()] = None,
) -> list[AdverseEventResponse]:
    views = await _service(session, pdp, audit).list_adverse_events(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        encounter_id=encounter_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_adverse_event_response(item) for item in views]


@router.get("/adverse-events/{adverse_event_id}", response_model=AdverseEventResponse)
async def get_adverse_event(
    adverse_event_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> AdverseEventResponse:
    view = await _service(session, pdp, audit).get_adverse_event(
        principal,
        adverse_event_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _adverse_event_response(view)


@router.post(
    "/adverse-events/{adverse_event_id}/amend",
    response_model=AdverseEventResponse,
)
async def amend_adverse_event(
    adverse_event_id: UUID,
    body: AmendAdverseEventRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> AdverseEventResponse:
    view = await _service(session, pdp, audit).amend_adverse_event(
        principal,
        adverse_event_id,
        organization_id=organization_id,
        facility_id=facility_id,
        severity=body.severity,
        occurrence_at=body.occurrence_at,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _adverse_event_response(view)


@router.post(
    "/adverse-events/{adverse_event_id}/entered-in-error",
    response_model=AdverseEventResponse,
)
async def mark_adverse_event_entered_in_error(
    adverse_event_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> AdverseEventResponse:
    view = await _service(session, pdp, audit).mark_adverse_event_entered_in_error(
        principal,
        adverse_event_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _adverse_event_response(view)


def _family_history_response(view: FamilyHistoryView) -> FamilyHistoryResponse:
    return FamilyHistoryResponse(
        id=view.id,
        patient_identity_id=view.patient_identity_id,
        encounter_id=view.encounter_id,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
        relationship=view.relationship,
        category=view.category,
        code=_codeable(view.code),
        occurrence_at=view.occurrence_at,
        note_text=view.note_text,
        status=view.status,
        recorded_at=view.recorded_at,
        version=view.version,
    )


@router.post("/family-histories", response_model=FamilyHistoryResponse)
async def create_family_history(
    body: CreateFamilyHistoryRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> FamilyHistoryResponse:
    code = parse_codeable_concept(body.code.model_dump())
    if code is None:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    view = await _service(session, pdp, audit).create_family_history(
        principal,
        patient_identity_id=body.patient_identity_id,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        relationship=body.relationship,
        category=body.category,
        code=code,
        occurrence_at=body.occurrence_at,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _family_history_response(view)


@router.get("/family-histories", response_model=list[FamilyHistoryResponse])
async def list_family_histories(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID, Query()],
    encounter_id: Annotated[UUID | None, Query()] = None,
) -> list[FamilyHistoryResponse]:
    views = await _service(session, pdp, audit).list_family_histories(
        principal,
        patient_identity_id=patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        encounter_id=encounter_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [_family_history_response(item) for item in views]


@router.get("/family-histories/{family_history_id}", response_model=FamilyHistoryResponse)
async def get_family_history(
    family_history_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> FamilyHistoryResponse:
    view = await _service(session, pdp, audit).get_family_history(
        principal,
        family_history_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _family_history_response(view)


@router.post(
    "/family-histories/{family_history_id}/amend",
    response_model=FamilyHistoryResponse,
)
async def amend_family_history(
    family_history_id: UUID,
    body: AmendFamilyHistoryRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> FamilyHistoryResponse:
    view = await _service(session, pdp, audit).amend_family_history(
        principal,
        family_history_id,
        organization_id=organization_id,
        facility_id=facility_id,
        occurrence_at=body.occurrence_at,
        note_text=body.note_text,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _family_history_response(view)


@router.post(
    "/family-histories/{family_history_id}/entered-in-error",
    response_model=FamilyHistoryResponse,
)
async def mark_family_history_entered_in_error(
    family_history_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> FamilyHistoryResponse:
    view = await _service(session, pdp, audit).mark_family_history_entered_in_error(
        principal,
        family_history_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _family_history_response(view)
