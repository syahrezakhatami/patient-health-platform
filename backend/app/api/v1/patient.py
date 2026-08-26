from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.v1.deps import (
    CorrelationId,
    CurrentAudit,
    OptionalOrganizationId,
    RequestOrganizationId,
    RequestPurpose,
    RequiredPatientPrincipal,
    require_patient_audience,
)
from app.core.dependencies import CurrentAuth, CurrentPDP, DbSession
from app.core.errors import ForbiddenError
from app.modules.authorization.domain.purpose import Purpose
from app.modules.patient_access.application.services import PatientAccessService

router = APIRouter(
    prefix="/patient",
    tags=["patient"],
    dependencies=[Depends(require_patient_audience)],
)


class BindPatientAccountRequest(BaseModel):
    patient_identity_id: UUID = Field(..., description="Canonical MPI identity UUID")


def _service(session: DbSession, pdp: CurrentPDP, audit: CurrentAudit) -> PatientAccessService:
    return PatientAccessService(session, pdp, audit)


def _require_patient_purpose(purpose: str) -> None:
    if purpose != Purpose.PATIENT_ACCESS.value:
        raise ForbiddenError("Not authorized")


@router.post("/accounts")
async def bind_patient_account(
    body: BindPatientAccountRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    auth: CurrentAuth,
    organization_id: OptionalOrganizationId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    _require_patient_purpose(purpose)
    account = await _service(session, pdp, audit).bind_account(
        subject=auth.subject,
        patient_identity_id=body.patient_identity_id,
        organization_id=organization_id,
        correlation_id=correlation_id,
    )
    return {
        "id": str(account.id),
        "subject": account.subject,
        "patient_identity_id": str(account.patient_identity_id),
        "status": account.status.value,
    }


@router.get("/me")
async def read_patient_account(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: RequiredPatientPrincipal,
    organization_id: OptionalOrganizationId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    _require_patient_purpose(purpose)
    return await _service(session, pdp, audit).read_account(
        principal,
        organization_id=organization_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )


@router.get("/record-access")
async def authorize_patient_record_access(
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: RequiredPatientPrincipal,
    organization_id: RequestOrganizationId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
    patient_identity_id: Annotated[UUID | None, Query()] = None,
) -> dict[str, object]:
    _require_patient_purpose(purpose)
    requested = patient_identity_id or principal.canonical_patient_identity_id
    return await _service(session, pdp, audit).authorize_record_access(
        principal,
        requested_patient_identity_id=requested,
        organization_id=organization_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
