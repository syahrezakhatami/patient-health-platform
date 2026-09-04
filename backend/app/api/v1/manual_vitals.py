from uuid import UUID

from fastapi import APIRouter, Depends

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
from app.api.v1.manual_vitals_schemas import (
    CreateManualVitalMeasurementRequest,
    ManualVitalMeasurementOptionResponse,
    ManualVitalsWriteContextResponse,
)
from app.api.v1.schemas import CodeableConceptRequest, ObservationResponse
from app.core.dependencies import CurrentPDP, DbSession
from app.core.errors import NotFoundError
from app.modules.clinical.application.manual_vitals_service import ManualVitalsService
from app.modules.clinical.application.services import ObservationView

router = APIRouter(
    prefix="/organizations/{organization_id}/clinical/manual-vitals",
    tags=["manual-vitals"],
    dependencies=[Depends(require_staff_audience)],
)


def _service(session: DbSession, pdp: CurrentPDP, audit: CurrentAudit) -> ManualVitalsService:
    return ManualVitalsService(session, pdp, audit)


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


@router.get("/measurements", response_model=ManualVitalsWriteContextResponse)
async def get_manual_vitals_write_context(
    organization_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    actor_organization_id: RequestOrganizationId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> ManualVitalsWriteContextResponse:
    if actor_organization_id != organization_id:
        raise NotFoundError("Resource not found")
    context = await _service(session, pdp, audit).get_write_context(
        principal,
        organization_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return ManualVitalsWriteContextResponse(
        available=context.available,
        catalog_version=context.catalog_version,
        feature_version=context.feature_version,
        measurements=[
            ManualVitalMeasurementOptionResponse(
                measurement_key=item.measurement_key,
                display_unit=item.display_unit,
                canonical_concept=item.canonical_concept,
            )
            for item in context.measurements
        ],
    )


@router.post("/measurements", response_model=ObservationResponse)
async def create_manual_vital_measurement(
    organization_id: UUID,
    body: CreateManualVitalMeasurementRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    actor_organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    idempotency_key: RequiredIdempotencyKey,
) -> ObservationResponse:
    if actor_organization_id != organization_id:
        raise NotFoundError("Resource not found")
    observation = await _service(session, pdp, audit).create_measurement(
        principal,
        organization_id,
        expected_patient_identity_id=body.expected_patient_identity_id,
        encounter_id=body.encounter_id,
        measurement_key=body.measurement_key,
        value=body.value,
        effective_at=body.effective_at,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return _observation_response(observation)
