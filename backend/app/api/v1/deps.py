from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request

from app.core.correlation import get_correlation_id
from app.core.dependencies import CurrentAuth, CurrentPDP, DbSession
from app.core.errors import AppError, ForbiddenError, UnauthorizedError
from app.modules.audit.application.ports import AuditSink
from app.modules.audit.infrastructure.sqlalchemy_sink import SqlAlchemyAuditSink
from app.modules.authorization.domain.purpose import parse_purpose
from app.modules.iam.domain.models import Principal
from app.modules.iam.infrastructure.repositories import IamRepository
from app.modules.patient_access.application.services import PatientAccessService
from app.modules.patient_access.domain.models import PatientPrincipal


async def get_principal(auth: CurrentAuth, session: DbSession) -> Principal | None:
    return await IamRepository(session).load_principal(auth.subject)


async def require_principal(
    principal: Annotated[Principal | None, Depends(get_principal)],
) -> Principal:
    if principal is None:
        raise ForbiddenError("User is not provisioned")
    return principal


def get_audit_sink(session: DbSession) -> AuditSink:
    return SqlAlchemyAuditSink(session)


def get_purpose(x_purpose: Annotated[str | None, Header()] = None) -> str:
    return parse_purpose(x_purpose).value


def get_optional_organization_id(
    x_organization_id: Annotated[str | None, Header()] = None,
) -> UUID | None:
    if x_organization_id is None or not x_organization_id.strip():
        return None
    try:
        return UUID(x_organization_id)
    except ValueError as exc:
        raise AppError(
            "invalid_organization",
            "X-Organization-Id must be a UUID",
            status_code=422,
        ) from exc


def get_organization_id(
    organization_id: Annotated[UUID | None, Depends(get_optional_organization_id)],
) -> UUID:
    if organization_id is None:
        raise AppError("organization_required", "X-Organization-Id is required", status_code=422)
    return organization_id


def get_optional_facility_id(x_facility_id: Annotated[str | None, Header()] = None) -> UUID | None:
    if x_facility_id is None or not x_facility_id.strip():
        return None
    try:
        return UUID(x_facility_id)
    except ValueError as exc:
        raise AppError("invalid_facility", "X-Facility-Id must be a UUID", status_code=422) from exc


def request_correlation_id(request: Request) -> str:
    return get_correlation_id(request)


CurrentPrincipal = Annotated[Principal | None, Depends(get_principal)]
RequiredPrincipal = Annotated[Principal, Depends(require_principal)]
CurrentAudit = Annotated[AuditSink, Depends(get_audit_sink)]
RequestPurpose = Annotated[str, Depends(get_purpose)]
RequestOrganizationId = Annotated[UUID, Depends(get_organization_id)]
OptionalOrganizationId = Annotated[UUID | None, Depends(get_optional_organization_id)]
RequestFacilityId = Annotated[UUID | None, Depends(get_optional_facility_id)]
CorrelationId = Annotated[str, Depends(request_correlation_id)]


def require_staff_audience(auth: CurrentAuth, request: Request) -> None:
    settings = request.app.state.settings
    if auth.audience != settings.auth_audience:
        raise UnauthorizedError("Token audience is invalid")


def require_patient_audience(auth: CurrentAuth, request: Request) -> None:
    settings = request.app.state.settings
    if auth.audience != settings.auth_patient_audience:
        raise UnauthorizedError("Token audience is invalid")


def require_staff_or_platform_audience(auth: CurrentAuth, request: Request) -> None:
    settings = request.app.state.settings
    allowed = {settings.auth_audience, settings.auth_platform_audience}
    if auth.audience not in allowed:
        raise UnauthorizedError("Token audience is invalid")


async def get_patient_principal(
    auth: CurrentAuth,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
) -> PatientPrincipal | None:
    return await PatientAccessService(session, pdp, audit).resolve_principal(auth.subject)


async def require_patient_principal(
    principal: Annotated[PatientPrincipal | None, Depends(get_patient_principal)],
) -> PatientPrincipal:
    if principal is None:
        raise ForbiddenError("User is not provisioned")
    return principal


RequiredPatientPrincipal = Annotated[PatientPrincipal, Depends(require_patient_principal)]
StaffAudience = Annotated[None, Depends(require_staff_audience)]
PatientAudience = Annotated[None, Depends(require_patient_audience)]
StaffOrPlatformAudience = Annotated[None, Depends(require_staff_or_platform_audience)]
