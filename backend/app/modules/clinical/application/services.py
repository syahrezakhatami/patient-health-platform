from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.modules.audit.application.ports import AuditSink
from app.modules.audit.domain.events import AuditEvent
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.catalog import Permission
from app.modules.clinical.domain.enums import (
    ClinicalAuditAction,
    ClinicalNoteType,
    ClinicalProvenanceSubjectType,
    ClinicalRecordStatus,
    EncounterClass,
    EncounterStatus,
    ParticipationType,
)
from app.modules.clinical.domain.lifecycle import (
    assert_encounter_transition,
    assert_note_can_finalize,
    assert_note_can_mark_error,
    assert_note_is_draft,
)
from app.modules.clinical.domain.terminology import CodeableConcept
from app.modules.clinical.infrastructure.models import (
    ClinicalNoteModel,
    ClinicalProvenanceModel,
    EncounterModel,
    EncounterParticipantModel,
)
from app.modules.clinical.infrastructure.repositories import ClinicalRepository, utc_now
from app.modules.iam.domain.models import Principal
from app.modules.mpi.domain.enums import IdentityLifecycle
from app.modules.mpi.infrastructure.models import PatientIdentityModel
from app.modules.mpi.infrastructure.repositories import MpiRepository
from app.shared.enums import AuditResult, AuthorshipKind, InformationSource
from app.shared.types.ids import new_id


@dataclass(frozen=True, slots=True)
class EncounterView:
    id: UUID
    patient_identity_id: UUID
    organization_id: UUID
    facility_id: UUID | None
    encounter_class: EncounterClass
    status: EncounterStatus
    display_label: str
    started_at: datetime
    ended_at: datetime | None
    reason: CodeableConcept | None


@dataclass(frozen=True, slots=True)
class ClinicalNoteView:
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID
    organization_id: UUID
    facility_id: UUID | None
    note_type: ClinicalNoteType
    body_text: str
    record_status: ClinicalRecordStatus
    version: int
    authored_at: datetime
    finalized_at: datetime | None


class ClinicalService:
    def __init__(
        self,
        session: AsyncSession,
        pdp: PolicyDecisionPoint,
        audit: AuditSink,
    ) -> None:
        self._session = session
        self._pdp = pdp
        self._audit = audit
        self._clinical = ClinicalRepository(session)
        self._mpi = MpiRepository(session)

    async def create_encounter(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        encounter_class: EncounterClass,
        started_at: datetime | None,
        reason: CodeableConcept | None,
        purpose: str,
        correlation_id: str | None,
    ) -> EncounterView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ENCOUNTER_CREATE,
            resource_type="Encounter",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        if (
            IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
            and encounter_class is not EncounterClass.EMER
        ):
            raise AppError(
                "anonymous_encounter_not_emergency",
                "An anonymous identity may receive only an emergency encounter",
                status_code=409,
            )
        occurred = started_at or utc_now()
        encounter_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.ENCOUNTER,
            subject_id=encounter_id,
            organization_id=organization_id,
            facility_id=facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        encounter = EncounterModel(
            id=encounter_id,
            patient_identity_id=identity.id,
            organization_id=organization_id,
            facility_id=facility_id,
            encounter_class=encounter_class.value,
            status=EncounterStatus.IN_PROGRESS
            if encounter_class is EncounterClass.EMER
            else EncounterStatus.PLANNED,
            display_label=f"ENC-{encounter_id.hex[:8].upper()}",
            started_at=occurred,
            ended_at=None,
            reason_system=None if reason is None else reason.system,
            reason_code=None if reason is None else reason.code,
            reason_display=None if reason is None else reason.display,
            actor_id=None if principal is None else principal.user.id,
            provenance_id=provenance.id,
        )
        await self._clinical.add_encounter(encounter)
        if principal is not None:
            await self._clinical.add_participant(
                EncounterParticipantModel(
                    id=new_id(),
                    encounter_id=encounter.id,
                    actor_id=principal.user.id,
                    participation_type=ParticipationType.ATTENDING.value,
                )
            )
        await self._audit_success(
            ClinicalAuditAction.ENCOUNTER_CREATED,
            principal,
            organization_id,
            facility_id,
            identity.id,
            purpose,
            correlation_id,
            resource_id=encounter.id,
            metadata={"encounter_class": encounter.encounter_class, "purpose": purpose},
        )
        return _encounter_view(encounter)

    async def get_encounter(
        self,
        principal: Principal | None,
        encounter_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> EncounterView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ENCOUNTER_READ,
            resource_type="Encounter",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        encounter = await self._visible_encounter(principal, encounter_id, organization_id)
        return _encounter_view(encounter)

    async def list_encounters(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[EncounterView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ENCOUNTER_READ,
            resource_type="Encounter",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_encounters_for_patient(identity.id, organization_id)
        return [_encounter_view(item) for item in rows]

    async def change_encounter_status(
        self,
        principal: Principal | None,
        encounter_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        status: EncounterStatus,
        purpose: str,
        correlation_id: str | None,
    ) -> EncounterView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ENCOUNTER_UPDATE_STATUS,
            resource_type="Encounter",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        encounter = await self._visible_encounter(
            principal, encounter_id, organization_id, for_update=True
        )
        previous = EncounterStatus(encounter.status)
        assert_encounter_transition(previous, status)
        encounter.status = status.value
        if status in {
            EncounterStatus.FINISHED,
            EncounterStatus.CANCELLED,
            EncounterStatus.ENTERED_IN_ERROR,
        }:
            encounter.ended_at = encounter.ended_at or utc_now()
        await self._audit_success(
            ClinicalAuditAction.ENCOUNTER_STATUS_CHANGED,
            principal,
            organization_id,
            facility_id,
            encounter.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=encounter.id,
            metadata={"from": previous.value, "to": status.value, "purpose": purpose},
        )
        return _encounter_view(encounter)

    async def create_note(
        self,
        principal: Principal | None,
        *,
        encounter_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        note_type: ClinicalNoteType,
        body_text: str,
        purpose: str,
        correlation_id: str | None,
    ) -> ClinicalNoteView:
        body = _require_note_body(body_text)
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_NOTE_CREATE,
            resource_type="ClinicalNote",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        encounter = await self._visible_encounter(
            principal, encounter_id, organization_id, for_update=True
        )
        if EncounterStatus(encounter.status) in {
            EncounterStatus.CANCELLED,
            EncounterStatus.ENTERED_IN_ERROR,
        }:
            raise AppError(
                "encounter_not_documentable",
                "A cancelled or erroneous encounter cannot receive notes",
                status_code=409,
            )
        note_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.CLINICAL_NOTE,
            subject_id=note_id,
            organization_id=organization_id,
            facility_id=facility_id or encounter.facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        note = ClinicalNoteModel(
            id=note_id,
            patient_identity_id=encounter.patient_identity_id,
            encounter_id=encounter.id,
            organization_id=organization_id,
            facility_id=facility_id or encounter.facility_id,
            note_type=note_type.value,
            body_text=body,
            record_status=ClinicalRecordStatus.DRAFT.value,
            version=1,
            supersedes_id=None,
            content_hash=_content_hash(note_type.value, body),
            author_id=None if principal is None else principal.user.id,
            authored_at=utc_now(),
            finalized_at=None,
            provenance_id=provenance.id,
        )
        await self._clinical.add_note(note)
        await self._audit_success(
            ClinicalAuditAction.CLINICAL_NOTE_CREATED,
            principal,
            organization_id,
            note.facility_id,
            note.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=note.id,
            metadata={"note_type": note.note_type, "purpose": purpose},
        )
        return _note_view(note)

    async def get_note(
        self,
        principal: Principal | None,
        note_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ClinicalNoteView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_NOTE_READ,
            resource_type="ClinicalNote",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        note = await self._visible_note(principal, note_id, organization_id)
        return _note_view(note)

    async def update_draft_note(
        self,
        principal: Principal | None,
        note_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        body_text: str,
        purpose: str,
        correlation_id: str | None,
    ) -> ClinicalNoteView:
        body = _require_note_body(body_text)
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_NOTE_UPDATE_DRAFT,
            resource_type="ClinicalNote",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        note = await self._visible_note(principal, note_id, organization_id, for_update=True)
        assert_note_is_draft(ClinicalRecordStatus(note.record_status))
        note.body_text = body
        note.content_hash = _content_hash(note.note_type, body)
        note.version = note.version + 1
        await self._audit_success(
            ClinicalAuditAction.CLINICAL_NOTE_UPDATED,
            principal,
            organization_id,
            note.facility_id,
            note.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=note.id,
            metadata={"purpose": purpose},
        )
        return _note_view(note)

    async def finalize_note(
        self,
        principal: Principal | None,
        note_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ClinicalNoteView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_NOTE_FINALIZE,
            resource_type="ClinicalNote",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        note = await self._visible_note(principal, note_id, organization_id, for_update=True)
        assert_note_can_finalize(ClinicalRecordStatus(note.record_status))
        note.record_status = ClinicalRecordStatus.FINAL.value
        note.finalized_at = utc_now()
        await self._audit_success(
            ClinicalAuditAction.CLINICAL_NOTE_FINALIZED,
            principal,
            organization_id,
            note.facility_id,
            note.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=note.id,
            metadata={"purpose": purpose},
        )
        return _note_view(note)

    async def mark_note_entered_in_error(
        self,
        principal: Principal | None,
        note_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ClinicalNoteView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_NOTE_FINALIZE,
            resource_type="ClinicalNote",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        note = await self._visible_note(principal, note_id, organization_id, for_update=True)
        assert_note_can_mark_error(ClinicalRecordStatus(note.record_status))
        note.record_status = ClinicalRecordStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.CLINICAL_NOTE_ENTERED_IN_ERROR,
            principal,
            organization_id,
            note.facility_id,
            note.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=note.id,
            metadata={"purpose": purpose},
        )
        return _note_view(note)

    async def _require_canonical_identity(
        self,
        principal: Principal | None,
        identity_id: UUID,
        organization_id: UUID,
    ) -> PatientIdentityModel:
        await self._require_visible_identity(principal, identity_id, organization_id)
        canonical = await self._mpi.resolve_canonical_identity(identity_id)
        if canonical is None:
            raise AppError(
                "canonical_resolution_failed",
                "Identity cannot be resolved to a canonical active identity",
                status_code=409,
            )
        return canonical

    async def _require_visible_identity(
        self,
        principal: Principal | None,
        identity_id: UUID,
        organization_id: UUID,
    ) -> PatientIdentityModel:
        identity = await self._mpi.get_identity(identity_id)
        if identity is None:
            raise NotFoundError("Patient identity not found")
        if not await self._identity_visible(principal, identity, organization_id):
            raise NotFoundError("Patient identity not found")
        if IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.RETIRED:
            raise AppError(
                "identity_not_usable",
                "A retired identity cannot receive clinical records",
                status_code=409,
            )
        return identity

    async def _identity_visible(
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

    async def _visible_encounter(
        self,
        principal: Principal | None,
        encounter_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> EncounterModel:
        if for_update:
            encounter = await self._clinical.get_encounter_for_update(encounter_id)
        else:
            encounter = await self._clinical.get_encounter(encounter_id)
        if encounter is None:
            raise NotFoundError("Encounter not found")
        if principal is not None and principal.has_platform_scope:
            return encounter
        if encounter.organization_id != organization_id:
            raise NotFoundError("Encounter not found")
        return encounter

    async def _visible_note(
        self,
        principal: Principal | None,
        note_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> ClinicalNoteModel:
        if for_update:
            note = await self._clinical.get_note_for_update(note_id)
        else:
            note = await self._clinical.get_note(note_id)
        if note is None:
            raise NotFoundError("Clinical note not found")
        if principal is not None and principal.has_platform_scope:
            return note
        if note.organization_id != organization_id:
            raise NotFoundError("Clinical note not found")
        return note

    async def _record_provenance(
        self,
        *,
        subject_type: ClinicalProvenanceSubjectType,
        subject_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        actor_id: UUID | None,
    ) -> ClinicalProvenanceModel:
        model = ClinicalProvenanceModel(
            id=new_id(),
            subject_type=subject_type.value,
            subject_id=subject_id,
            source_organization_id=organization_id,
            source_facility_id=facility_id,
            actor_id=actor_id,
            recorded_at=utc_now(),
            verification_method="clinical_authorship",
            authorship_kind=AuthorshipKind.NATIVE.value,
            information_source=InformationSource.CLINICIAN.value,
        )
        return await self._clinical.add_provenance(model)

    async def _audit_success(
        self,
        action: ClinicalAuditAction,
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
                resource_type="ClinicalRecord",
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


def _require_note_body(body_text: str) -> str:
    body = body_text.strip()
    if not body:
        raise AppError("note_body_required", "Clinical note body is required", status_code=422)
    if len(body) > 20_000:
        raise AppError("note_body_too_long", "Clinical note body exceeds 20000 characters", 422)
    return body


def _content_hash(note_type: str, body: str) -> str:
    return sha256(f"{note_type}\n{body}".encode()).hexdigest()


def _encounter_view(model: EncounterModel) -> EncounterView:
    reason = None
    if model.reason_system and model.reason_code:
        reason = CodeableConcept(
            system=model.reason_system,
            code=model.reason_code,
            display=model.reason_display,
        )
    return EncounterView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        encounter_class=EncounterClass(model.encounter_class),
        status=EncounterStatus(model.status),
        display_label=model.display_label,
        started_at=model.started_at,
        ended_at=model.ended_at,
        reason=reason,
    )


def _note_view(model: ClinicalNoteModel) -> ClinicalNoteView:
    return ClinicalNoteView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        note_type=ClinicalNoteType(model.note_type),
        body_text=model.body_text,
        record_status=ClinicalRecordStatus(model.record_status),
        version=model.version,
        authored_at=model.authored_at,
        finalized_at=model.finalized_at,
    )
