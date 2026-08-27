from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.audit.application.ports import AuditSink
from app.modules.audit.domain.events import AuditEvent
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.purpose import Purpose
from app.modules.iam.domain.models import Principal
from app.modules.mpi.domain.enums import (
    AdministrativeSex,
    AuditAction,
    ClusterMembershipStatus,
    ClusterStatus,
    IdentifierType,
    IdentifierVerificationStatus,
    IdentityKind,
    IdentityLifecycle,
    MatchCandidateStatus,
    MatchDecision,
    MatchProbeStatus,
    MergeOperationStatus,
    MergeOperationType,
    PatientLookupOutcome,
    PatientLookupType,
    ProvenanceSubjectType,
)
from app.modules.mpi.domain.evidence import parse_merge_evidence
from app.modules.mpi.domain.identifiers import (
    is_sensitive_identifier,
    mask_identifier,
    normalize_identifier,
    normalize_person_name,
    requires_organization,
)
from app.modules.mpi.domain.lifecycle import assert_transition
from app.modules.mpi.domain.matching import (
    DeterministicMatchingEngine,
    IdentifierProbe,
    IdentityProbe,
    MatchResult,
)
from app.modules.mpi.domain.merge import MergeValidation, validate_merge, validate_unmerge
from app.modules.mpi.domain.patient_lookup import (
    CANONICAL_LOOKUP_SYSTEM,
    LOOKUP_TYPE_TO_IDENTIFIER,
    MAX_PATIENT_LOOKUP_RESULTS,
    NATIONAL_LOOKUP_TYPES,
    PATIENT_LOOKUP_FETCH_LIMIT,
    lookup_system_for,
    parse_patient_identity_uuid,
)
from app.modules.mpi.infrastructure.models import (
    IdentityClusterMemberModel,
    IdentityClusterModel,
    IdentityMatchCandidateModel,
    IdentityMatchProbeModel,
    IdentityMergeOperationModel,
    IdentityProvenanceModel,
    PatientIdentifierModel,
    PatientIdentityModel,
)
from app.modules.mpi.infrastructure.repositories import MpiRepository, utc_now
from app.modules.organization.infrastructure.repositories import OrganizationRepository
from app.shared.enums import AuditResult, AuthorshipKind, InformationSource
from app.shared.types.ids import new_id


@dataclass(frozen=True, slots=True)
class IdentifierInput:
    identifier_system: str
    identifier_type: IdentifierType
    identifier_value: str
    organization_id: UUID | None = None
    facility_id: UUID | None = None
    source_system: str | None = None
    source_record_id: str | None = None


@dataclass(frozen=True, slots=True)
class IdentityView:
    id: UUID
    lifecycle_status: IdentityLifecycle
    identity_kind: IdentityKind
    display_label: str
    given_name: str | None
    family_name: str | None
    birth_date: date | None
    administrative_sex: AdministrativeSex | None
    surviving_identity_id: UUID | None
    identifiers: tuple["IdentifierView", ...]


@dataclass(frozen=True, slots=True)
class IdentifierView:
    id: UUID
    identifier_system: str
    identifier_type: IdentifierType
    masked_value: str
    verification_status: IdentifierVerificationStatus
    organization_id: UUID | None
    facility_id: UUID | None


@dataclass(frozen=True, slots=True)
class PatientLookupHit:
    patient_identity_id: UUID
    requested_patient_identity_id: UUID | None
    lifecycle_status: IdentityLifecycle
    identity_kind: IdentityKind
    display_name: str
    display_label: str
    birth_date: date | None
    administrative_sex: AdministrativeSex | None
    organization_mrn: str | None
    masked_identifier: str | None
    identifier_verification: IdentifierVerificationStatus | None
    resolved_from_merged: bool
    review_required: bool
    selectable: bool


@dataclass(frozen=True, slots=True)
class PatientLookupView:
    outcome: PatientLookupOutcome
    truncated: bool
    results: tuple[PatientLookupHit, ...]


class MpiService:
    def __init__(
        self,
        session: AsyncSession,
        pdp: PolicyDecisionPoint,
        audit: AuditSink,
    ) -> None:
        self._session = session
        self._pdp = pdp
        self._audit = audit
        self._mpi = MpiRepository(session)
        self._orgs = OrganizationRepository(session)
        self._matcher = DeterministicMatchingEngine()

    async def create_identity(
        self,
        principal: Principal | None,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        given_name: str | None,
        family_name: str | None,
        birth_date: date | None,
        administrative_sex: AdministrativeSex | None,
        identifiers: list[IdentifierInput],
        purpose: str,
        correlation_id: str | None,
        source_system: str | None,
        source_record_id: str | None,
    ) -> IdentityView:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_IDENTITY_CREATE,
            resource_type="PatientIdentity",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        if not identifiers:
            raise AppError(
                "identifier_required",
                "Identified registration requires at least one identifier",
                status_code=422,
            )
        identity = await self._insert_identity(
            lifecycle=IdentityLifecycle.ACTIVE,
            kind=IdentityKind.STANDARD,
            given_name=given_name,
            family_name=family_name,
            birth_date=birth_date,
            administrative_sex=administrative_sex,
        )
        try:
            for item in identifiers:
                await self._insert_identifier(
                    identity.id,
                    item,
                    default_organization_id=organization_id,
                    default_facility_id=facility_id,
                )
        except IntegrityError as exc:
            raise ConflictError("An identity with this identifier already exists") from exc
        await self._create_cluster(identity.id)
        await self._record_provenance(
            subject_type=ProvenanceSubjectType.PATIENT_IDENTITY,
            subject_id=identity.id,
            organization_id=organization_id,
            facility_id=facility_id,
            actor_id=None if principal is None else principal.user.id,
            source_system=source_system,
            source_record_id=source_record_id,
        )
        await self._audit_success(
            AuditAction.PATIENT_IDENTITY_CREATED,
            principal,
            organization_id,
            facility_id,
            identity.id,
            purpose,
            correlation_id,
        )
        return await self._to_view(identity)

    async def create_anonymous_identity(
        self,
        principal: Principal | None,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
        source_system: str | None,
        source_record_id: str | None,
        temporary: bool = False,
    ) -> IdentityView:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_IDENTITY_CREATE,
            resource_type="PatientIdentity",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        kind = IdentityKind.TEMPORARY if temporary else IdentityKind.ANONYMOUS
        identity = await self._insert_identity(
            lifecycle=IdentityLifecycle.ANONYMOUS,
            kind=kind,
            given_name=None,
            family_name=None,
            birth_date=None,
            administrative_sex=None,
        )
        await self._create_cluster(identity.id)
        await self._record_provenance(
            subject_type=ProvenanceSubjectType.PATIENT_IDENTITY,
            subject_id=identity.id,
            organization_id=organization_id,
            facility_id=facility_id,
            actor_id=None if principal is None else principal.user.id,
            source_system=source_system,
            source_record_id=source_record_id,
        )
        await self._audit_success(
            AuditAction.ANONYMOUS_IDENTITY_CREATED,
            principal,
            organization_id,
            facility_id,
            identity.id,
            purpose,
            correlation_id,
        )
        return await self._to_view(identity)

    async def get_identity(
        self,
        principal: Principal | None,
        identity_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> IdentityView:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_IDENTITY_READ,
            resource_type="PatientIdentity",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._mpi.get_identity(identity_id)
        if identity is None or not await self._is_visible(principal, identity, organization_id):
            raise NotFoundError("Patient identity not found")
        return await self._to_view(identity)

    async def lookup_by_identifier(
        self,
        principal: Principal | None,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        identifier_system: str,
        identifier_type: IdentifierType,
        identifier_value: str,
        identifier_organization_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> IdentityView:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_IDENTITY_READ,
            resource_type="PatientIdentity",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        normalized = normalize_identifier(identifier_system, identifier_type, identifier_value)
        scoped_org = identifier_organization_id
        if requires_organization(identifier_type):
            scoped_org = identifier_organization_id or organization_id
        found = await self._mpi.find_active_identifier(
            identifier_system.strip(),
            normalized.normalized_value,
            scoped_org,
        )
        if found is None:
            raise NotFoundError("Patient identity not found")
        return await self.get_identity(
            principal,
            found.patient_identity_id,
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )

    async def lookup_patients(
        self,
        principal: Principal | None,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        lookup_type: PatientLookupType,
        lookup_value: str,
        purpose: str,
        correlation_id: str | None,
    ) -> PatientLookupView:
        if purpose == Purpose.PATIENT_ACCESS.value:
            raise AppError(
                "purpose_principal_mismatch",
                "PATIENT_ACCESS is not valid for staff patient lookup",
                status_code=403,
            )
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_IDENTITY_READ,
            resource_type="PatientIdentity",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        if lookup_type is PatientLookupType.PATIENT_IDENTITY_ID:
            view = await self._lookup_patients_by_uuid(
                principal,
                organization_id=organization_id,
                lookup_value=lookup_value,
            )
        else:
            view = await self._lookup_patients_by_identifier(
                principal,
                organization_id=organization_id,
                lookup_type=lookup_type,
                lookup_value=lookup_value,
            )
        canonical_id = None
        if view.outcome is PatientLookupOutcome.ONE:
            canonical_id = view.results[0].patient_identity_id
        await self._audit_success(
            AuditAction.PATIENT_LOOKUP_ACCESSED,
            principal,
            organization_id,
            facility_id,
            canonical_id,
            purpose,
            correlation_id,
            resource_id=canonical_id,
            metadata={
                "lookup_type": lookup_type.value,
                "outcome": view.outcome.value,
                "result_count": str(len(view.results)),
                "truncated": "true" if view.truncated else "false",
            },
        )
        return view

    async def _lookup_patients_by_uuid(
        self,
        principal: Principal | None,
        *,
        organization_id: UUID,
        lookup_value: str,
    ) -> PatientLookupView:
        try:
            identity_id = parse_patient_identity_uuid(lookup_value)
        except ValueError as exc:
            raise AppError(
                "invalid_identifier",
                "Patient identity id must be a UUID",
                status_code=422,
            ) from exc
        source = await self._mpi.get_identity(identity_id)
        if source is None or not await self._is_org_visible(principal, source, organization_id):
            return _empty_lookup()
        lifecycle = IdentityLifecycle(source.lifecycle_status)
        if lifecycle is IdentityLifecycle.RETIRED:
            raise AppError(
                "identity_not_usable",
                "This identity cannot be selected",
                status_code=409,
            )
        canonical = await self._mpi.resolve_canonical_identity(identity_id)
        if canonical is None:
            raise AppError(
                "identity_not_usable",
                "This identity cannot be selected",
                status_code=409,
            )
        if not await self._is_org_visible(principal, canonical, organization_id):
            return _empty_lookup()
        if IdentityLifecycle(canonical.lifecycle_status) is IdentityLifecycle.RETIRED:
            raise AppError(
                "identity_not_usable",
                "This identity cannot be selected",
                status_code=409,
            )
        hit = await self._to_lookup_hit(
            canonical,
            requested_id=identity_id,
            organization_id=organization_id,
            lookup_type=PatientLookupType.PATIENT_IDENTITY_ID,
            hit_identifier=None,
        )
        return PatientLookupView(
            outcome=PatientLookupOutcome.ONE,
            truncated=False,
            results=(hit,),
        )

    async def _lookup_patients_by_identifier(
        self,
        principal: Principal | None,
        *,
        organization_id: UUID,
        lookup_type: PatientLookupType,
        lookup_value: str,
    ) -> PatientLookupView:
        identifier_type = LOOKUP_TYPE_TO_IDENTIFIER[lookup_type]
        system = lookup_system_for(lookup_type, identifier_type)
        normalized = normalize_identifier(system, identifier_type, lookup_value)
        scoped_org = organization_id if requires_organization(identifier_type) else None
        rows = await self._mpi.find_active_identifiers_for_lookup(
            identifier_type=identifier_type,
            normalized_value=normalized.normalized_value,
            organization_id=scoped_org,
            identifier_system=CANONICAL_LOOKUP_SYSTEM.get(lookup_type),
            limit=PATIENT_LOOKUP_FETCH_LIMIT,
        )
        hits_by_canonical: dict[UUID, PatientLookupHit] = {}
        for row in rows:
            source = await self._mpi.get_identity(row.patient_identity_id)
            if source is None or not await self._is_org_visible(principal, source, organization_id):
                continue
            if IdentityLifecycle(source.lifecycle_status) is IdentityLifecycle.RETIRED:
                continue
            canonical = await self._mpi.resolve_canonical_identity(source.id)
            if canonical is None:
                continue
            if not await self._is_org_visible(principal, canonical, organization_id):
                continue
            if IdentityLifecycle(canonical.lifecycle_status) is IdentityLifecycle.RETIRED:
                continue
            if canonical.id in hits_by_canonical:
                continue
            hits_by_canonical[canonical.id] = await self._to_lookup_hit(
                canonical,
                requested_id=source.id,
                organization_id=organization_id,
                lookup_type=lookup_type,
                hit_identifier=row,
            )
        ordered = tuple(hits_by_canonical.values())
        truncated = len(ordered) > MAX_PATIENT_LOOKUP_RESULTS or (
            len(rows) >= PATIENT_LOOKUP_FETCH_LIMIT and len(ordered) >= MAX_PATIENT_LOOKUP_RESULTS
        )
        bounded = ordered[:MAX_PATIENT_LOOKUP_RESULTS]
        if not bounded:
            return _empty_lookup()
        if len(bounded) == 1 and bounded[0].selectable:
            outcome = PatientLookupOutcome.ONE
        elif len(bounded) == 1:
            outcome = PatientLookupOutcome.REVIEW_REQUIRED
        elif any(item.selectable for item in bounded):
            outcome = PatientLookupOutcome.AMBIGUOUS
        else:
            outcome = PatientLookupOutcome.REVIEW_REQUIRED
        return PatientLookupView(outcome=outcome, truncated=truncated, results=bounded)

    async def _to_lookup_hit(
        self,
        canonical: PatientIdentityModel,
        *,
        requested_id: UUID,
        organization_id: UUID,
        lookup_type: PatientLookupType,
        hit_identifier: PatientIdentifierModel | None,
    ) -> PatientLookupHit:
        identifiers = await self._mpi.list_identifiers(canonical.id)
        sex = canonical.administrative_sex
        verification = None
        masked = None
        review_required = False
        if hit_identifier is not None:
            verification = IdentifierVerificationStatus(hit_identifier.verification_status)
            if lookup_type in NATIONAL_LOOKUP_TYPES:
                masked = mask_identifier(hit_identifier.normalized_value)
                review_required = verification is not IdentifierVerificationStatus.VERIFIED
        selectable = not review_required
        given = (canonical.given_name or "").strip()
        family = (canonical.family_name or "").strip()
        display_name = " ".join(part for part in (given, family) if part) or canonical.display_label
        return PatientLookupHit(
            patient_identity_id=canonical.id,
            requested_patient_identity_id=None if requested_id == canonical.id else requested_id,
            lifecycle_status=IdentityLifecycle(canonical.lifecycle_status),
            identity_kind=IdentityKind(canonical.identity_kind),
            display_name=display_name,
            display_label=canonical.display_label,
            birth_date=canonical.birth_date,
            administrative_sex=None if sex is None else AdministrativeSex(sex),
            organization_mrn=_organization_mrn(identifiers, organization_id, hit_identifier),
            masked_identifier=masked,
            identifier_verification=verification,
            resolved_from_merged=requested_id != canonical.id,
            review_required=review_required,
            selectable=selectable,
        )

    async def add_identifier(
        self,
        principal: Principal | None,
        identity_id: UUID,
        item: IdentifierInput,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> IdentifierView:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_IDENTIFIER_ADD,
            resource_type="PatientIdentifier",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_visible_identity(principal, identity_id, organization_id)
        if IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.MERGED:
            raise AppError("invalid_identity", "Cannot add identifiers to a merged identity", 409)
        try:
            model = await self._insert_identifier(
                identity.id,
                item,
                default_organization_id=organization_id,
                default_facility_id=facility_id,
            )
        except IntegrityError as exc:
            raise ConflictError("This identifier is already assigned") from exc
        await self._record_provenance(
            subject_type=ProvenanceSubjectType.IDENTIFIER,
            subject_id=model.id,
            organization_id=organization_id,
            facility_id=facility_id,
            actor_id=None if principal is None else principal.user.id,
            source_system=item.source_system,
            source_record_id=item.source_record_id,
        )
        await self._audit_success(
            AuditAction.IDENTIFIER_ADDED,
            principal,
            organization_id,
            facility_id,
            identity.id,
            purpose,
            correlation_id,
            resource_id=model.id,
            metadata={"identifier_type": item.identifier_type.value},
        )
        return _identifier_view(model)

    async def verify_identifier(
        self,
        principal: Principal | None,
        identifier_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        method: str,
        purpose: str,
        correlation_id: str | None,
    ) -> IdentifierView:
        return await self._set_verification(
            principal,
            identifier_id,
            status=IdentifierVerificationStatus.VERIFIED,
            organization_id=organization_id,
            facility_id=facility_id,
            method=method,
            purpose=purpose,
            correlation_id=correlation_id,
            action=AuditAction.IDENTIFIER_VERIFIED,
        )

    async def reject_identifier(
        self,
        principal: Principal | None,
        identifier_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        method: str,
        purpose: str,
        correlation_id: str | None,
    ) -> IdentifierView:
        return await self._set_verification(
            principal,
            identifier_id,
            status=IdentifierVerificationStatus.REJECTED,
            organization_id=organization_id,
            facility_id=facility_id,
            method=method,
            purpose=purpose,
            correlation_id=correlation_id,
            action=AuditAction.IDENTIFIER_REJECTED,
        )

    async def identify_anonymous(
        self,
        principal: Principal | None,
        identity_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        given_name: str | None,
        family_name: str | None,
        birth_date: date | None,
        administrative_sex: AdministrativeSex | None,
        identifiers: list[IdentifierInput],
        reason: str,
        purpose: str,
        correlation_id: str | None,
    ) -> IdentityView:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_IDENTIFIER_ADD,
            resource_type="PatientIdentity",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_visible_identity(principal, identity_id, organization_id)
        current = IdentityLifecycle(identity.lifecycle_status)
        if current is not IdentityLifecycle.ANONYMOUS:
            raise AppError(
                "invalid_identity",
                "Only an anonymous identity can be identified in place",
                409,
            )
        if not reason.strip():
            raise AppError(
                "reason_required",
                "Identity resolution requires an explicit reason",
                422,
            )
        assert_transition(current, IdentityLifecycle.ACTIVE)
        identity.lifecycle_status = IdentityLifecycle.ACTIVE
        identity.identity_kind = IdentityKind.STANDARD
        identity.given_name = given_name
        identity.family_name = family_name
        identity.birth_date = birth_date
        identity.administrative_sex = (
            None if administrative_sex is None else administrative_sex.value
        )
        identity.name_normalized = normalize_person_name(given_name, family_name)
        try:
            for item in identifiers:
                await self._insert_identifier(
                    identity.id,
                    item,
                    default_organization_id=organization_id,
                    default_facility_id=facility_id,
                )
        except IntegrityError as exc:
            raise ConflictError("An identity with this identifier already exists") from exc
        await self._record_provenance(
            subject_type=ProvenanceSubjectType.IDENTITY_RESOLUTION,
            subject_id=identity.id,
            organization_id=organization_id,
            facility_id=facility_id,
            actor_id=None if principal is None else principal.user.id,
            source_system=None,
            source_record_id=None,
            verification_method="identity_resolution",
        )
        await self._audit_success(
            AuditAction.IDENTITY_RESOLUTION_COMPLETED,
            principal,
            organization_id,
            facility_id,
            identity.id,
            purpose,
            correlation_id,
            metadata={"reason": reason.strip()},
        )
        await self._audit_success(
            AuditAction.IDENTITY_STATUS_CHANGED,
            principal,
            organization_id,
            facility_id,
            identity.id,
            purpose,
            correlation_id,
            metadata={"from": current.value, "to": IdentityLifecycle.ACTIVE.value},
        )
        return await self._to_view(identity)

    async def match(
        self,
        principal: Principal | None,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        identity_id: UUID | None,
        given_name: str | None,
        family_name: str | None,
        birth_date: date | None,
        identifiers: list[IdentifierInput],
        purpose: str,
        correlation_id: str | None,
    ) -> list[MatchResult]:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_MATCH_EVALUATE,
            resource_type="IdentityMatch",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        if (
            identity_id is None
            and not identifiers
            and not (given_name and family_name and birth_date)
        ):
            raise AppError(
                "insufficient_match_criteria",
                "Matching requires an identity, a trusted identifier, or name plus birth date",
                status_code=422,
            )
        probe_identifiers = tuple(_to_probe(item) for item in identifiers)
        name_normalized = normalize_person_name(given_name, family_name)
        resolved_identity_id = identity_id
        if identity_id is not None:
            canonical = await self._mpi.resolve_canonical_identity(identity_id)
            if canonical is None:
                raise AppError(
                    "canonical_resolution_failed",
                    "Identity cannot be resolved to a canonical active identity",
                    status_code=409,
                )
            stored = await self._mpi.load_canonical_stored_identities([identity_id])
            current = stored[0] if stored else None
            resolved_identity_id = canonical.id
            probe = IdentityProbe(
                identity_id=canonical.id,
                given_name=given_name or None,
                family_name=family_name or None,
                name_normalized=name_normalized
                or (None if current is None else current.name_normalized),
                birth_date=birth_date or (None if current is None else current.birth_date),
                identifiers=(() if current is None else current.identifiers) + probe_identifiers,
            )
        else:
            probe = IdentityProbe(
                identity_id=None,
                given_name=given_name,
                family_name=family_name,
                name_normalized=name_normalized,
                birth_date=birth_date,
                identifiers=probe_identifiers,
            )
        keys = [
            (item.identifier_system, item.normalized_value, item.organization_id)
            for item in probe.identifiers
        ]
        candidates = await self._mpi.list_match_candidates_for_probe(
            name_normalized=probe.name_normalized,
            birth_date=probe.birth_date,
            identifier_keys=keys,
        )
        results = self._matcher.match(probe, candidates)
        persistable = [
            item
            for item in results
            if item.decision
            in {
                MatchDecision.POSSIBLE_MATCH,
                MatchDecision.PROBABLE_MATCH,
                MatchDecision.CONFIRMED_MATCH,
                MatchDecision.REQUIRES_REVIEW,
            }
        ]
        if resolved_identity_id is not None:
            for item in persistable:
                await self._upsert_match_candidate(
                    resolved_identity_id,
                    item,
                    principal,
                    organization_id,
                    purpose,
                    correlation_id,
                )
        else:
            await self._persist_probe_only_matches(
                results,
                principal,
                organization_id,
                facility_id,
                purpose,
                correlation_id,
            )
        return results

    async def review_match(
        self,
        principal: Principal | None,
        candidate_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        decision: MatchDecision,
        reason: str,
        purpose: str,
        correlation_id: str | None,
    ) -> None:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_MATCH_REVIEW,
            resource_type="IdentityMatchCandidate",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        candidate = await self._mpi.get_match_candidate(candidate_id)
        if candidate is None:
            raise NotFoundError("Match candidate not found")
        if not reason.strip():
            raise AppError("reason_required", "Match review requires an explicit reason", 422)
        candidate.status = MatchCandidateStatus.REVIEWED
        candidate.review_decision = decision.value
        candidate.reviewer_id = None if principal is None else principal.user.id
        candidate.reviewed_at = utc_now()
        candidate.review_reason = reason.strip()
        await self._audit_success(
            AuditAction.MATCH_REVIEWED,
            principal,
            organization_id,
            facility_id,
            candidate.left_identity_id,
            purpose,
            correlation_id,
            resource_id=candidate.id,
            metadata={"decision": decision.value},
        )

    async def merge(
        self,
        principal: Principal | None,
        *,
        source_id: UUID,
        target_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        reason: str,
        evidence: list[dict[str, str]],
        purpose: str,
        correlation_id: str | None,
        idempotency_key: str | None,
    ) -> IdentityMergeOperationModel:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_MERGE_EXECUTE,
            resource_type="IdentityMerge",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=target_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        if not reason.strip():
            raise AppError("reason_required", "Merge requires an explicit reason", 422)
        evidence_items = parse_merge_evidence(evidence)
        if idempotency_key:
            existing = await self._mpi.get_merge_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
        source, target = await self._lock_visible_identities(
            principal,
            organization_id,
            source_id,
            target_id,
        )
        replay = await self._mpi.get_completed_merge(source.id, target.id)
        if replay is not None:
            return replay
        source_ids = await self._mpi.list_identifiers(source.id)
        target_ids = await self._mpi.list_identifiers(target.id)
        validate_merge(
            MergeValidation(
                source_id=source.id,
                target_id=target.id,
                source_status=IdentityLifecycle(source.lifecycle_status),
                target_status=IdentityLifecycle(target.lifecycle_status),
                source_surviving_id=source.surviving_identity_id,
                target_surviving_id=target.surviving_identity_id,
                source_identifiers=tuple(_model_to_probe(item) for item in source_ids),
                target_identifiers=tuple(_model_to_probe(item) for item in target_ids),
            )
        )
        if IdentityLifecycle(source.lifecycle_status) is IdentityLifecycle.MERGED:
            existing = await self._mpi.get_completed_merge(source.id, target.id)
            if existing is not None:
                return existing
        previous = IdentityLifecycle(source.lifecycle_status)
        assert_transition(previous, IdentityLifecycle.MERGED)
        source.lifecycle_status = IdentityLifecycle.MERGED
        source.surviving_identity_id = target.id
        await self._relocate_cluster_member(source.id, target.id)
        provenance = await self._record_provenance(
            subject_type=ProvenanceSubjectType.MERGE_OPERATION,
            subject_id=source.id,
            organization_id=organization_id,
            facility_id=facility_id,
            actor_id=None if principal is None else principal.user.id,
            source_system=None,
            source_record_id=None,
            verification_method="explicit_merge",
        )
        operation = IdentityMergeOperationModel(
            id=new_id(),
            source_identity_id=source.id,
            target_identity_id=target.id,
            operation=MergeOperationType.MERGE,
            status=MergeOperationStatus.COMPLETED,
            reason=reason.strip(),
            actor_id=new_id() if principal is None else principal.user.id,
            organization_id=organization_id,
            facility_id=facility_id,
            evidence=[item.as_stored() for item in evidence_items],
            related_merge_id=None,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            provenance_id=provenance.id,
            occurred_at=utc_now(),
        )
        try:
            await self._mpi.add_merge_operation(operation)
        except IntegrityError as exc:
            if idempotency_key:
                existing = await self._mpi.get_merge_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            raise ConflictError("Merge operation conflict") from exc
        await self._audit_success(
            AuditAction.PATIENT_MERGED,
            principal,
            organization_id,
            facility_id,
            target.id,
            purpose,
            correlation_id,
            resource_id=operation.id,
            metadata={
                "source_identity_id": str(source.id),
                "purpose": purpose,
                "evidence_types": ",".join(item.evidence_type.value for item in evidence_items),
            },
        )
        await self._audit_success(
            AuditAction.IDENTITY_STATUS_CHANGED,
            principal,
            organization_id,
            facility_id,
            source.id,
            purpose,
            correlation_id,
            metadata={"from": previous.value, "to": IdentityLifecycle.MERGED.value},
        )
        return operation

    async def unmerge(
        self,
        principal: Principal | None,
        *,
        merge_operation_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        reason: str,
        evidence: list[dict[str, str]],
        purpose: str,
        correlation_id: str | None,
        idempotency_key: str | None,
    ) -> IdentityMergeOperationModel:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_UNMERGE_EXECUTE,
            resource_type="IdentityUnmerge",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        if not reason.strip():
            raise AppError("reason_required", "Unmerge requires an explicit reason", 422)
        evidence_items = parse_merge_evidence(evidence)
        if idempotency_key:
            existing = await self._mpi.get_merge_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
        original = await self._mpi.get_merge_operation(merge_operation_id)
        if original is None or original.operation != MergeOperationType.MERGE:
            raise NotFoundError("Merge operation not found")
        source, _target = await self._lock_visible_identities(
            principal,
            organization_id,
            original.source_identity_id,
            original.target_identity_id,
        )
        validate_unmerge(
            IdentityLifecycle(source.lifecycle_status),
            source.surviving_identity_id,
            original.target_identity_id,
        )
        previous = IdentityLifecycle(source.lifecycle_status)
        assert_transition(previous, IdentityLifecycle.ACTIVE)
        source.lifecycle_status = IdentityLifecycle.ACTIVE
        source.surviving_identity_id = None
        await self._restore_cluster(source.id)
        provenance = await self._record_provenance(
            subject_type=ProvenanceSubjectType.MERGE_OPERATION,
            subject_id=source.id,
            organization_id=organization_id,
            facility_id=facility_id,
            actor_id=None if principal is None else principal.user.id,
            source_system=None,
            source_record_id=None,
            verification_method="explicit_unmerge",
        )
        operation = IdentityMergeOperationModel(
            id=new_id(),
            source_identity_id=source.id,
            target_identity_id=original.target_identity_id,
            operation=MergeOperationType.UNMERGE,
            status=MergeOperationStatus.COMPLETED,
            reason=reason.strip(),
            actor_id=new_id() if principal is None else principal.user.id,
            organization_id=organization_id,
            facility_id=facility_id,
            evidence=[item.as_stored() for item in evidence_items],
            related_merge_id=original.id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            provenance_id=provenance.id,
            occurred_at=utc_now(),
        )
        try:
            await self._mpi.add_merge_operation(operation)
        except IntegrityError as exc:
            if idempotency_key:
                existing = await self._mpi.get_merge_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            raise ConflictError("Unmerge operation conflict") from exc
        await self._audit_success(
            AuditAction.PATIENT_UNMERGED,
            principal,
            organization_id,
            facility_id,
            source.id,
            purpose,
            correlation_id,
            resource_id=operation.id,
            metadata={"original_merge_id": str(original.id)},
        )
        await self._audit_success(
            AuditAction.IDENTITY_STATUS_CHANGED,
            principal,
            organization_id,
            facility_id,
            source.id,
            purpose,
            correlation_id,
            metadata={"from": previous.value, "to": IdentityLifecycle.ACTIVE.value},
        )
        return operation

    async def _set_verification(
        self,
        principal: Principal | None,
        identifier_id: UUID,
        *,
        status: IdentifierVerificationStatus,
        organization_id: UUID,
        facility_id: UUID | None,
        method: str,
        purpose: str,
        correlation_id: str | None,
        action: AuditAction,
    ) -> IdentifierView:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.MPI_IDENTIFIER_VERIFY,
            resource_type="PatientIdentifier",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        model = await self._mpi.get_identifier(identifier_id)
        if model is None:
            raise NotFoundError("Identifier not found")
        await self._require_visible_identity(principal, model.patient_identity_id, organization_id)
        if not method.strip():
            raise AppError("verification_method_required", "Verification method is required", 422)
        model.verification_status = status
        model.verification_method = method.strip()
        model.verified_by = None if principal is None else principal.user.id
        model.verified_at = utc_now()
        await self._record_provenance(
            subject_type=ProvenanceSubjectType.IDENTIFIER,
            subject_id=model.id,
            organization_id=organization_id,
            facility_id=facility_id,
            actor_id=None if principal is None else principal.user.id,
            source_system=model.source_system,
            source_record_id=model.source_record_id,
            verification_method=method.strip(),
        )
        await self._audit_success(
            action,
            principal,
            organization_id,
            facility_id,
            model.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=model.id,
            metadata={"status": status.value},
        )
        return _identifier_view(model)

    async def _insert_identity(
        self,
        *,
        lifecycle: IdentityLifecycle,
        kind: IdentityKind,
        given_name: str | None,
        family_name: str | None,
        birth_date: date | None,
        administrative_sex: AdministrativeSex | None,
    ) -> PatientIdentityModel:
        identity_id = new_id()
        prefix = "TEMP" if kind is IdentityKind.TEMPORARY else "UNKNOWN"
        if kind is IdentityKind.STANDARD:
            prefix = "ID"
        model = PatientIdentityModel(
            id=identity_id,
            lifecycle_status=lifecycle.value,
            identity_kind=kind.value,
            display_label=f"{prefix}-{identity_id.hex[:8].upper()}",
            given_name=given_name,
            family_name=family_name,
            name_normalized=normalize_person_name(given_name, family_name),
            birth_date=birth_date,
            administrative_sex=None if administrative_sex is None else administrative_sex.value,
            surviving_identity_id=None,
        )
        return await self._mpi.add_identity(model)

    async def _insert_identifier(
        self,
        identity_id: UUID,
        item: IdentifierInput,
        *,
        default_organization_id: UUID,
        default_facility_id: UUID | None,
    ) -> PatientIdentifierModel:
        organization_id = item.organization_id
        if requires_organization(item.identifier_type):
            organization_id = organization_id or default_organization_id
            if organization_id is None:
                raise AppError(
                    "organization_required",
                    "This identifier requires an organization",
                    422,
                )
            if await self._orgs.get_organization(organization_id) is None:
                raise NotFoundError("Organization not found")
        elif organization_id is None and item.identifier_type is IdentifierType.OTHER:
            organization_id = None
        normalized = normalize_identifier(
            item.identifier_system,
            item.identifier_type,
            item.identifier_value,
        )
        model = PatientIdentifierModel(
            id=new_id(),
            patient_identity_id=identity_id,
            organization_id=organization_id,
            facility_id=item.facility_id or default_facility_id,
            identifier_system=item.identifier_system.strip(),
            identifier_type=item.identifier_type.value,
            identifier_value=normalized.raw_value,
            normalized_value=normalized.normalized_value,
            matching_value=normalized.matching_value,
            verification_status=IdentifierVerificationStatus.UNVERIFIED,
            verification_method=None,
            source_system=item.source_system,
            source_record_id=item.source_record_id,
        )
        return await self._mpi.add_identifier(model)

    async def _create_cluster(self, identity_id: UUID) -> None:
        cluster = await self._mpi.add_cluster(
            IdentityClusterModel(
                id=new_id(),
                canonical_identity_id=identity_id,
                status=ClusterStatus.ACTIVE,
            )
        )
        await self._mpi.add_cluster_member(
            IdentityClusterMemberModel(
                id=new_id(),
                cluster_id=cluster.id,
                identity_id=identity_id,
                membership_status=ClusterMembershipStatus.ACTIVE,
                valid_from=utc_now(),
                valid_to=None,
            )
        )

    async def _relocate_cluster_member(self, source_id: UUID, target_id: UUID) -> None:
        source_member = await self._mpi.active_cluster_member(source_id)
        target_member = await self._mpi.active_cluster_member(target_id)
        now = utc_now()
        if source_member is not None:
            source_member.valid_to = now
            source_member.membership_status = ClusterMembershipStatus.MERGED_IN
        if target_member is None:
            return
        await self._mpi.add_cluster_member(
            IdentityClusterMemberModel(
                id=new_id(),
                cluster_id=target_member.cluster_id,
                identity_id=source_id,
                membership_status=ClusterMembershipStatus.MERGED_IN,
                valid_from=now,
                valid_to=None,
            )
        )

    async def _restore_cluster(self, identity_id: UUID) -> None:
        current = await self._mpi.active_cluster_member(identity_id)
        now = utc_now()
        if current is not None:
            current.valid_to = now
            current.membership_status = ClusterMembershipStatus.UNMERGED
        await self._create_cluster(identity_id)

    async def _persist_probe_only_matches(
        self,
        results: list[MatchResult],
        principal: Principal | None,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> None:
        persistable = [
            item
            for item in results
            if item.decision
            in {
                MatchDecision.POSSIBLE_MATCH,
                MatchDecision.PROBABLE_MATCH,
                MatchDecision.CONFIRMED_MATCH,
                MatchDecision.REQUIRES_REVIEW,
            }
        ]
        rows: list[MatchResult | None] = list(persistable) if persistable else [None]
        for item in rows:
            probe_id = new_id()
            provenance = await self._record_provenance(
                subject_type=ProvenanceSubjectType.MATCH_CANDIDATE,
                subject_id=probe_id,
                organization_id=organization_id,
                facility_id=facility_id,
                actor_id=None if principal is None else principal.user.id,
                source_system=None,
                source_record_id=None,
                verification_method="deterministic-v1",
            )
            probe = IdentityMatchProbeModel(
                id=probe_id,
                candidate_identity_id=None if item is None else item.candidate_patient_id,
                actor_id=None if principal is None else principal.user.id,
                organization_id=organization_id,
                facility_id=facility_id,
                purpose=purpose,
                algorithm_version="deterministic-v1" if item is None else item.algorithm_version,
                decision=None if item is None else item.decision.value,
                score=None if item is None else str(item.score),
                confidence=None if item is None else item.confidence,
                evidence_types=[] if item is None else list(item.evidence),
                reasons=[] if item is None else list(item.reasons),
                correlation_id=correlation_id,
                provenance_id=provenance.id,
                status=(
                    MatchProbeStatus.PROBE_ONLY
                    if item is None
                    else MatchProbeStatus.MATCHED_CANDIDATE
                ),
                occurred_at=utc_now(),
            )
            await self._mpi.add_match_probe(probe)
            await self._audit_success(
                AuditAction.MATCH_CANDIDATE_CREATED,
                principal,
                organization_id,
                facility_id,
                None if item is None else item.candidate_patient_id,
                purpose,
                correlation_id,
                resource_id=probe.id,
                metadata={
                    "purpose": purpose,
                    "probe_status": probe.status,
                    "decision": probe.decision or "none",
                },
            )

    async def _upsert_match_candidate(
        self,
        identity_id: UUID,
        result: MatchResult,
        principal: Principal | None,
        organization_id: UUID,
        purpose: str,
        correlation_id: str | None,
    ) -> None:
        left, right = sorted([identity_id, result.candidate_patient_id])
        existing = await self._mpi.find_match_pair(left, right)
        if existing is not None:
            existing.score = str(result.score)
            existing.confidence = result.confidence
            existing.decision = result.decision.value
            existing.reasons = list(result.reasons)
            existing.evidence = list(result.evidence)
            existing.algorithm_version = result.algorithm_version
            existing.status = MatchCandidateStatus.OPEN
            return
        model = IdentityMatchCandidateModel(
            id=new_id(),
            left_identity_id=left,
            right_identity_id=right,
            score=str(result.score),
            confidence=result.confidence,
            decision=result.decision.value,
            reasons=list(result.reasons),
            evidence=list(result.evidence),
            algorithm_version=result.algorithm_version,
            status=MatchCandidateStatus.OPEN,
        )
        await self._mpi.add_match_candidate(model)
        await self._audit_success(
            AuditAction.MATCH_CANDIDATE_CREATED,
            principal,
            organization_id,
            None,
            identity_id,
            purpose,
            correlation_id,
            resource_id=model.id,
            metadata={"decision": result.decision.value},
        )

    async def _record_provenance(
        self,
        *,
        subject_type: ProvenanceSubjectType,
        subject_id: UUID,
        organization_id: UUID | None,
        facility_id: UUID | None,
        actor_id: UUID | None,
        source_system: str | None,
        source_record_id: str | None,
        verification_method: str | None = None,
    ) -> IdentityProvenanceModel:
        model = IdentityProvenanceModel(
            id=new_id(),
            subject_type=subject_type.value,
            subject_id=subject_id,
            source_organization_id=organization_id,
            source_facility_id=facility_id,
            source_system=source_system,
            source_record_id=source_record_id,
            actor_id=actor_id,
            recorded_at=utc_now(),
            imported_at=None,
            verification_method=verification_method,
            authorship_kind=AuthorshipKind.NATIVE,
            information_source=InformationSource.CLINICIAN,
        )
        return await self._mpi.add_provenance(model)

    async def _lock_visible_identities(
        self,
        principal: Principal | None,
        organization_id: UUID,
        *identity_ids: UUID,
    ) -> tuple[PatientIdentityModel, ...]:
        locked: dict[UUID, PatientIdentityModel] = {}
        for identity_id in sorted(set(identity_ids)):
            identity = await self._mpi.get_identity_for_update(identity_id)
            if identity is None or not await self._is_visible(principal, identity, organization_id):
                raise NotFoundError("Patient identity not found")
            locked[identity_id] = identity
        return tuple(locked[identity_id] for identity_id in identity_ids)

    async def _require_visible_identity(
        self,
        principal: Principal | None,
        identity_id: UUID,
        organization_id: UUID,
    ) -> PatientIdentityModel:
        identity = await self._mpi.get_identity(identity_id)
        if identity is None or not await self._is_visible(principal, identity, organization_id):
            raise NotFoundError("Patient identity not found")
        return identity

    async def _is_visible(
        self,
        principal: Principal | None,
        identity: PatientIdentityModel,
        organization_id: UUID,
    ) -> bool:
        if principal is not None and principal.has_platform_scope:
            return True
        provenances = await self._mpi.list_provenances(identity.id)
        if any(item.source_organization_id == organization_id for item in provenances):
            return True
        identifiers = await self._mpi.list_identifiers(identity.id)
        return any(item.organization_id == organization_id for item in identifiers)

    async def _is_org_visible(
        self,
        principal: Principal | None,
        identity: PatientIdentityModel,
        organization_id: UUID,
    ) -> bool:
        """Tenant visibility for Healthcare Web lookup. No platform superuser bypass."""
        del principal
        provenances = await self._mpi.list_provenances(identity.id)
        if any(item.source_organization_id == organization_id for item in provenances):
            return True
        identifiers = await self._mpi.list_identifiers(identity.id)
        return any(item.organization_id == organization_id for item in identifiers)

    async def _to_view(self, identity: PatientIdentityModel) -> IdentityView:
        identifiers = await self._mpi.list_identifiers(identity.id)
        sex = identity.administrative_sex
        return IdentityView(
            id=identity.id,
            lifecycle_status=IdentityLifecycle(identity.lifecycle_status),
            identity_kind=IdentityKind(identity.identity_kind),
            display_label=identity.display_label,
            given_name=identity.given_name,
            family_name=identity.family_name,
            birth_date=identity.birth_date,
            administrative_sex=None if sex is None else AdministrativeSex(sex),
            surviving_identity_id=identity.surviving_identity_id,
            identifiers=tuple(_identifier_view(item) for item in identifiers),
        )

    async def _audit_success(
        self,
        action: AuditAction,
        principal: Principal | None,
        organization_id: UUID | None,
        facility_id: UUID | None,
        patient_id: UUID | None,
        purpose: str | None,
        correlation_id: str | None,
        *,
        resource_id: UUID | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        await self._audit.record(
            AuditEvent(
                action=action.value,
                resource_type="PatientIdentity",
                result=AuditResult.SUCCESS,
                actor_id=None if principal is None else principal.user.id,
                organization_id=organization_id,
                facility_id=facility_id,
                resource_id=resource_id or patient_id,
                patient_id=patient_id,
                purpose=purpose,
                correlation_id=correlation_id,
                metadata={**(metadata or {}), "purpose": purpose or ""},
            )
        )


def _identifier_view(model: PatientIdentifierModel) -> IdentifierView:
    identifier_type = IdentifierType(model.identifier_type)
    value = (
        mask_identifier(model.identifier_value)
        if is_sensitive_identifier(identifier_type)
        else model.identifier_value
    )
    return IdentifierView(
        id=model.id,
        identifier_system=model.identifier_system,
        identifier_type=identifier_type,
        masked_value=value,
        verification_status=IdentifierVerificationStatus(model.verification_status),
        organization_id=model.organization_id,
        facility_id=model.facility_id,
    )


def _to_probe(item: IdentifierInput) -> IdentifierProbe:
    normalized = normalize_identifier(
        item.identifier_system,
        item.identifier_type,
        item.identifier_value,
    )
    return IdentifierProbe(
        identifier_system=item.identifier_system.strip(),
        identifier_type=item.identifier_type,
        normalized_value=normalized.normalized_value,
        organization_id=item.organization_id,
        verification_status=IdentifierVerificationStatus.UNVERIFIED,
    )


def _model_to_probe(model: PatientIdentifierModel) -> IdentifierProbe:
    return IdentifierProbe(
        identifier_system=model.identifier_system,
        identifier_type=IdentifierType(model.identifier_type),
        normalized_value=model.normalized_value,
        organization_id=model.organization_id,
        verification_status=IdentifierVerificationStatus(model.verification_status),
    )


def _empty_lookup() -> PatientLookupView:
    return PatientLookupView(outcome=PatientLookupOutcome.NONE, truncated=False, results=())


def _organization_mrn(
    identifiers: list[PatientIdentifierModel],
    organization_id: UUID,
    hit_identifier: PatientIdentifierModel | None,
) -> str | None:
    org_mrns = [
        item.identifier_value
        for item in identifiers
        if item.identifier_type == IdentifierType.MRN.value
        and item.organization_id == organization_id
        and item.valid_to is None
    ]
    if org_mrns:
        return org_mrns[0]
    if (
        hit_identifier is not None
        and hit_identifier.identifier_type == IdentifierType.MRN.value
        and hit_identifier.organization_id == organization_id
    ):
        return hit_identifier.identifier_value
    return None
