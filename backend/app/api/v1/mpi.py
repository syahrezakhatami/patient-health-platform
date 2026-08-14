from uuid import UUID

from fastapi import APIRouter

from app.api.v1.deps import (
    CorrelationId,
    CurrentAudit,
    CurrentPrincipal,
    RequestFacilityId,
    RequestOrganizationId,
    RequestPurpose,
)
from app.api.v1.schemas import (
    CreateAnonymousIdentityRequest,
    CreateIdentityRequest,
    IdentifierRequest,
    IdentifierResponse,
    IdentifyAnonymousRequest,
    IdentityResponse,
    LookupIdentityRequest,
    MatchRequest,
    MatchResultResponse,
    MergeOperationResponse,
    MergeRequest,
    ReviewMatchRequest,
    UnmergeRequest,
    VerifyIdentifierRequest,
)
from app.core.dependencies import CurrentPDP, DbSession
from app.modules.mpi.application.services import IdentifierInput, IdentityView, MpiService

router = APIRouter(prefix="/mpi", tags=["mpi"])


def _service(session: DbSession, pdp: CurrentPDP, audit: CurrentAudit) -> MpiService:
    return MpiService(session, pdp, audit)


def _identifier_input(item: IdentifierRequest) -> IdentifierInput:
    return IdentifierInput(
        identifier_system=item.identifier_system,
        identifier_type=item.identifier_type,
        identifier_value=item.identifier_value,
        organization_id=item.organization_id,
        facility_id=item.facility_id,
        source_system=item.source_system,
        source_record_id=item.source_record_id,
    )


def _identity_response(view: IdentityView) -> IdentityResponse:
    return IdentityResponse(
        id=view.id,
        lifecycle_status=view.lifecycle_status,
        identity_kind=view.identity_kind,
        display_label=view.display_label,
        given_name=view.given_name,
        family_name=view.family_name,
        birth_date=view.birth_date,
        administrative_sex=view.administrative_sex,
        surviving_identity_id=view.surviving_identity_id,
        identifiers=[
            IdentifierResponse(
                id=item.id,
                identifier_system=item.identifier_system,
                identifier_type=item.identifier_type,
                masked_value=item.masked_value,
                verification_status=item.verification_status,
                organization_id=item.organization_id,
                facility_id=item.facility_id,
            )
            for item in view.identifiers
        ],
    )


@router.post("/identities", response_model=IdentityResponse)
async def create_identity(
    body: CreateIdentityRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> IdentityResponse:
    view = await _service(session, pdp, audit).create_identity(
        principal,
        organization_id=organization_id,
        facility_id=facility_id,
        given_name=body.given_name,
        family_name=body.family_name,
        birth_date=body.birth_date,
        administrative_sex=body.administrative_sex,
        identifiers=[_identifier_input(item) for item in body.identifiers],
        purpose=purpose,
        correlation_id=correlation_id,
        source_system=body.source_system,
        source_record_id=body.source_record_id,
    )
    return _identity_response(view)


@router.post("/identities/anonymous", response_model=IdentityResponse)
async def create_anonymous_identity(
    body: CreateAnonymousIdentityRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> IdentityResponse:
    view = await _service(session, pdp, audit).create_anonymous_identity(
        principal,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
        source_system=body.source_system,
        source_record_id=body.source_record_id,
        temporary=body.temporary,
    )
    return _identity_response(view)


@router.post("/identities/lookup", response_model=IdentityResponse)
async def lookup_identity(
    body: LookupIdentityRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> IdentityResponse:
    view = await _service(session, pdp, audit).lookup_by_identifier(
        principal,
        organization_id=organization_id,
        facility_id=facility_id,
        identifier_system=body.identifier_system,
        identifier_type=body.identifier_type,
        identifier_value=body.identifier_value,
        identifier_organization_id=body.identifier_organization_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _identity_response(view)


@router.get("/identities/{identity_id}", response_model=IdentityResponse)
async def get_identity(
    identity_id: UUID,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> IdentityResponse:
    view = await _service(session, pdp, audit).get_identity(
        principal,
        identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _identity_response(view)


@router.post("/identities/{identity_id}/identifiers", response_model=IdentifierResponse)
async def add_identifier(
    identity_id: UUID,
    body: IdentifierRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> IdentifierResponse:
    view = await _service(session, pdp, audit).add_identifier(
        principal,
        identity_id,
        _identifier_input(body),
        organization_id=organization_id,
        facility_id=facility_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return IdentifierResponse(
        id=view.id,
        identifier_system=view.identifier_system,
        identifier_type=view.identifier_type,
        masked_value=view.masked_value,
        verification_status=view.verification_status,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
    )


@router.post("/identities/{identity_id}/identify", response_model=IdentityResponse)
async def identify_anonymous(
    identity_id: UUID,
    body: IdentifyAnonymousRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> IdentityResponse:
    view = await _service(session, pdp, audit).identify_anonymous(
        principal,
        identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        given_name=body.given_name,
        family_name=body.family_name,
        birth_date=body.birth_date,
        administrative_sex=body.administrative_sex,
        identifiers=[_identifier_input(item) for item in body.identifiers],
        reason=body.reason,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return _identity_response(view)


@router.post("/identifiers/{identifier_id}/verify", response_model=IdentifierResponse)
async def verify_identifier(
    identifier_id: UUID,
    body: VerifyIdentifierRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> IdentifierResponse:
    view = await _service(session, pdp, audit).verify_identifier(
        principal,
        identifier_id,
        organization_id=organization_id,
        facility_id=facility_id,
        method=body.method,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return IdentifierResponse(
        id=view.id,
        identifier_system=view.identifier_system,
        identifier_type=view.identifier_type,
        masked_value=view.masked_value,
        verification_status=view.verification_status,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
    )


@router.post("/identifiers/{identifier_id}/reject", response_model=IdentifierResponse)
async def reject_identifier(
    identifier_id: UUID,
    body: VerifyIdentifierRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> IdentifierResponse:
    view = await _service(session, pdp, audit).reject_identifier(
        principal,
        identifier_id,
        organization_id=organization_id,
        facility_id=facility_id,
        method=body.method,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return IdentifierResponse(
        id=view.id,
        identifier_system=view.identifier_system,
        identifier_type=view.identifier_type,
        masked_value=view.masked_value,
        verification_status=view.verification_status,
        organization_id=view.organization_id,
        facility_id=view.facility_id,
    )


@router.post("/match", response_model=list[MatchResultResponse])
async def match_identities(
    body: MatchRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> list[MatchResultResponse]:
    results = await _service(session, pdp, audit).match(
        principal,
        organization_id=organization_id,
        facility_id=facility_id,
        identity_id=body.identity_id,
        given_name=body.given_name,
        family_name=body.family_name,
        birth_date=body.birth_date,
        identifiers=[_identifier_input(item) for item in body.identifiers],
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return [
        MatchResultResponse(
            candidate_patient_id=item.candidate_patient_id,
            score=item.score,
            confidence=item.confidence,
            decision=item.decision,
            reasons=list(item.reasons),
            evidence=list(item.evidence),
            algorithm_version=item.algorithm_version,
        )
        for item in results
    ]


@router.post("/match-candidates/{candidate_id}/review")
async def review_match(
    candidate_id: UUID,
    body: ReviewMatchRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> dict[str, str]:
    await _service(session, pdp, audit).review_match(
        principal,
        candidate_id,
        organization_id=organization_id,
        facility_id=facility_id,
        decision=body.decision,
        reason=body.reason,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    return {"status": "reviewed"}


@router.post("/merge", response_model=MergeOperationResponse)
async def merge_identities(
    body: MergeRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> MergeOperationResponse:
    operation = await _service(session, pdp, audit).merge(
        principal,
        source_id=body.source_identity_id,
        target_id=body.target_identity_id,
        organization_id=organization_id,
        facility_id=facility_id,
        reason=body.reason,
        evidence=[item.model_dump(mode="json") for item in body.evidence],
        purpose=purpose,
        correlation_id=correlation_id,
        idempotency_key=body.idempotency_key,
    )
    return MergeOperationResponse(
        id=operation.id,
        source_identity_id=operation.source_identity_id,
        target_identity_id=operation.target_identity_id,
        operation=operation.operation,
        status=operation.status,
        reason=operation.reason,
        related_merge_id=operation.related_merge_id,
    )


@router.post("/unmerge", response_model=MergeOperationResponse)
async def unmerge_identities(
    body: UnmergeRequest,
    session: DbSession,
    pdp: CurrentPDP,
    audit: CurrentAudit,
    principal: CurrentPrincipal,
    organization_id: RequestOrganizationId,
    facility_id: RequestFacilityId,
    purpose: RequestPurpose,
    correlation_id: CorrelationId,
) -> MergeOperationResponse:
    operation = await _service(session, pdp, audit).unmerge(
        principal,
        merge_operation_id=body.merge_operation_id,
        organization_id=organization_id,
        facility_id=facility_id,
        reason=body.reason,
        evidence=[item.model_dump(mode="json") for item in body.evidence],
        purpose=purpose,
        correlation_id=correlation_id,
        idempotency_key=body.idempotency_key,
    )
    return MergeOperationResponse(
        id=operation.id,
        source_identity_id=operation.source_identity_id,
        target_identity_id=operation.target_identity_id,
        operation=operation.operation,
        status=operation.status,
        reason=operation.reason,
        related_merge_id=operation.related_merge_id,
    )
