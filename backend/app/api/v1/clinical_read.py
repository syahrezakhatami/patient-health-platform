from datetime import datetime
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
    require_staff_audience,
)
from app.core.dependencies import CurrentPDP, DbSession
from app.modules.clinical_read.application.schemas import (
    ChartShellResponse,
    ClinicalSummaryResponse,
    SectionPageResponse,
    TimelinePageResponse,
)
from app.modules.clinical_read.application.services import ClinicalReadService
from app.modules.clinical_read.domain.catalog import parse_section
from app.modules.clinical_read.domain.cursor import ChartCursor, decode_cursor

router = APIRouter(
    prefix="/clinical/patients",
    tags=["clinical-read"],
    dependencies=[Depends(require_staff_audience)],
)


def _service(session: DbSession, pdp: CurrentPDP, audit: CurrentAudit) -> ClinicalReadService:
    return ClinicalReadService(session, pdp, audit)


def _optional_cursor(raw: str | None) -> ChartCursor | None:
    if raw is None or not raw.strip():
        return None
    return decode_cursor(raw.strip())


@router.get(
    "/{patient_identity_id}/chart",
    response_model=ChartShellResponse,
)
async def get_chart_shell(
    patient_identity_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    encounter_id: Annotated[UUID | None, Query()] = None,
    query_facility_id: Annotated[UUID | None, Query(alias="facility_id")] = None,
) -> ChartShellResponse:
    return await _service(session, pdp, audit).get_chart_shell(
        principal,
        patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
        encounter_id=encounter_id,
        query_facility_id=query_facility_id,
    )


@router.get(
    "/{patient_identity_id}/chart/summary",
    response_model=ClinicalSummaryResponse,
    response_model_exclude_none=True,
)
async def get_chart_summary(
    patient_identity_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    encounter_id: Annotated[UUID | None, Query()] = None,
    query_facility_id: Annotated[UUID | None, Query(alias="facility_id")] = None,
) -> ClinicalSummaryResponse:
    return await _service(session, pdp, audit).get_summary(
        principal,
        patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
        encounter_id=encounter_id,
        query_facility_id=query_facility_id,
    )


@router.get("/{patient_identity_id}/chart/timeline", response_model=TimelinePageResponse)
async def get_chart_timeline(
    patient_identity_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    encounter_id: Annotated[UUID | None, Query()] = None,
    query_facility_id: Annotated[UUID | None, Query(alias="facility_id")] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    recorded_from: Annotated[datetime | None, Query()] = None,
    recorded_to: Annotated[datetime | None, Query()] = None,
) -> TimelinePageResponse:
    return await _service(session, pdp, audit).get_timeline(
        principal,
        patient_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
        encounter_id=encounter_id,
        query_facility_id=query_facility_id,
        cursor=_optional_cursor(cursor),
        limit=limit,
        recorded_from=recorded_from,
        recorded_to=recorded_to,
    )


@router.get(
    "/{patient_identity_id}/chart/sections/{section}",
    response_model=SectionPageResponse,
)
async def get_chart_section(
    patient_identity_id: UUID,
    section: str,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    encounter_id: Annotated[UUID | None, Query()] = None,
    query_facility_id: Annotated[UUID | None, Query(alias="facility_id")] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    recorded_from: Annotated[datetime | None, Query()] = None,
    recorded_to: Annotated[datetime | None, Query()] = None,
) -> SectionPageResponse:
    return await _service(session, pdp, audit).get_section(
        principal,
        patient_identity_id,
        parse_section(section),
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
        encounter_id=encounter_id,
        query_facility_id=query_facility_id,
        cursor=_optional_cursor(cursor),
        limit=limit,
        status=status,
        category=category,
        recorded_from=recorded_from,
        recorded_to=recorded_to,
    )
