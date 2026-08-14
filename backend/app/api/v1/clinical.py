from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.deps import (
    CorrelationId,
    CurrentAudit,
    CurrentPrincipal,
    RequestFacilityId,
    RequestOrganizationId,
    RequestPurpose,
)
from app.api.v1.schemas import (
    AmendLaboratoryResultRequest,
    AmendObservationRequest,
    ChangeConditionStatusRequest,
    ChangeEncounterStatusRequest,
    ClinicalNoteResponse,
    CodeableConceptRequest,
    ConditionResponse,
    CreateClinicalNoteRequest,
    CreateConditionRequest,
    CreateEncounterRequest,
    CreateLaboratoryOrderRequest,
    CreateLaboratoryResultRequest,
    CreateLaboratorySpecimenRequest,
    CreateMedicationRequest,
    CreateObservationRequest,
    EncounterResponse,
    LaboratoryOrderResponse,
    LaboratoryResultResponse,
    LaboratorySpecimenResponse,
    MedicationResponse,
    ObservationResponse,
    UpdateClinicalNoteRequest,
)
from app.core.dependencies import CurrentPDP, DbSession
from app.core.errors import AppError
from app.modules.clinical.application.services import (
    ClinicalNoteView,
    ClinicalService,
    ConditionView,
    EncounterView,
    LaboratoryOrderView,
    LaboratoryResultView,
    LaboratorySpecimenView,
    MedicationView,
    ObservationView,
)
from app.modules.clinical.domain.laboratory_values import (
    LaboratoryResultValue,
    parse_laboratory_result_value,
)
from app.modules.clinical.domain.observation_values import ObservationValue, parse_observation_value
from app.modules.clinical.domain.terminology import CodeableConcept, parse_codeable_concept

router = APIRouter(prefix="/clinical", tags=["clinical"])


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
) -> ClinicalNoteResponse:
    view = await _service(session, pdp, audit).create_note(
        principal,
        encounter_id=body.encounter_id,
        organization_id=organization_id,
        facility_id=facility_id,
        note_type=body.note_type,
        body_text=body.body_text,
        purpose=purpose,
        correlation_id=correlation_id,
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
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ClinicalNoteResponse:
    view = await _service(session, pdp, audit).finalize_note(
        principal,
        note_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
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
