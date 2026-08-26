from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.modules.audit.application.ports import AuditSink
from app.modules.audit.domain.events import AuditEvent
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.purpose import Purpose
from app.modules.clinical.infrastructure.models import (
    LaboratoryResultModel,
    LaboratorySpecimenModel,
)
from app.modules.clinical_read.application.presenters import (
    adverse_event_dto,
    allergy_dto,
    condition_dto,
    consent_dto,
    dump_dto,
    encounter_dto,
    family_history_dto,
    immunization_dto,
    lab_order_dto,
    lab_result_dto,
    lab_specimen_dto,
    medical_device_dto,
    medication_dto,
    note_list_dto,
    observation_dto,
    procedure_dto,
    row_occurred_at,
    selected_encounter_dto,
    summary_item,
    timeline_item,
)
from app.modules.clinical_read.application.schemas import (
    ChartShellResponse,
    ClinicalSummaryResponse,
    PatientHeaderDTO,
    SectionPageResponse,
    TimelineItemDTO,
    TimelinePageResponse,
)
from app.modules.clinical_read.domain.age import age_years
from app.modules.clinical_read.domain.catalog import (
    SOURCE_PERMISSION,
    SUMMARY_ALLERGY_LIMIT,
    SUMMARY_CONDITION_LIMIT,
    SUMMARY_LAB_LIMIT,
    SUMMARY_MEDICATION_LIMIT,
    SUMMARY_PROCEDURE_LIMIT,
    SUMMARY_VITAL_LIMIT,
    authorized_sections,
    section_authorize_action,
    validate_section_filters,
)
from app.modules.clinical_read.domain.cursor import ChartCursor, encode_cursor, parse_limit
from app.modules.clinical_read.domain.enums import (
    ChartSection,
    ChartSurface,
    ClinicalReadAuditAction,
    TimelineSourceType,
)
from app.modules.clinical_read.domain.timeline import paginate_timeline
from app.modules.clinical_read.infrastructure.queries import ClinicalReadQueryRepository, FactQuery
from app.modules.iam.domain.models import Principal
from app.modules.mpi.domain.enums import IdentityLifecycle
from app.modules.mpi.infrastructure.models import PatientIdentityModel
from app.modules.mpi.infrastructure.repositories import MpiRepository
from app.modules.organization.infrastructure.repositories import OrganizationRepository
from app.shared.enums import AuditResult


@dataclass(frozen=True, slots=True)
class ChartContext:
    requested_id: UUID
    canonical: PatientIdentityModel
    cluster_ids: tuple[UUID, ...]
    organization_id: UUID
    header_facility_id: UUID | None
    purpose: str
    correlation_id: str | None
    principal: Principal | None
    scopes: frozenset[str]


class ClinicalReadService:
    def __init__(
        self,
        session: AsyncSession,
        pdp: PolicyDecisionPoint,
        audit: AuditSink,
    ) -> None:
        self._session = session
        self._pdp = pdp
        self._audit = audit
        self._queries = ClinicalReadQueryRepository(session)
        self._mpi = MpiRepository(session)
        self._organizations = OrganizationRepository(session)

    async def get_chart_shell(
        self,
        principal: Principal | None,
        patient_identity_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
        encounter_id: UUID | None,
        query_facility_id: UUID | None,
    ) -> ChartShellResponse:
        context = await self._open_chart(
            principal,
            patient_identity_id,
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
            encounter_id=encounter_id,
            query_facility_id=query_facility_id,
        )
        header = await self._header(context, encounter_id=encounter_id)
        sections = authorized_sections(context.scopes)
        await self._audit_chart_access(context, ChartSurface.SHELL, sections)
        return ChartShellResponse(
            requested_patient_identity_id=context.requested_id,
            canonical_patient_identity_id=context.canonical.id,
            header=header,
            authorized_sections=list(sections),
        )

    async def get_summary(
        self,
        principal: Principal | None,
        patient_identity_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
        encounter_id: UUID | None,
        query_facility_id: UUID | None,
    ) -> ClinicalSummaryResponse:
        context = await self._open_chart(
            principal,
            patient_identity_id,
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
            encounter_id=encounter_id,
            query_facility_id=query_facility_id,
        )
        sections = authorized_sections(context.scopes)
        payload = ClinicalSummaryResponse(
            requested_patient_identity_id=context.requested_id,
            canonical_patient_identity_id=context.canonical.id,
        )
        org = context.organization_id
        cluster = context.cluster_ids
        scope = {"encounter_id": encounter_id, "facility_id": query_facility_id}
        if Permission.CLINICAL_CONDITION_READ in context.scopes:
            condition_rows = await self._queries.summary_conditions(
                org, cluster, limit=SUMMARY_CONDITION_LIMIT, **scope
            )
            if condition_rows:
                payload = payload.model_copy(
                    update={
                        "active_conditions": [
                            summary_item(
                                source_type=TimelineSourceType.CONDITION.value,
                                source_id=row.id,
                                code_system=row.code_system,
                                code=row.code,
                                code_display=row.code_display,
                                status=row.clinical_status,
                                occurred_at=row_occurred_at(row, TimelineSourceType.CONDITION),
                            )
                            for row in condition_rows
                        ]
                    }
                )
        if Permission.CLINICAL_MEDICATION_READ in context.scopes:
            medication_rows = await self._queries.summary_medications(
                org, cluster, limit=SUMMARY_MEDICATION_LIMIT, **scope
            )
            if medication_rows:
                payload = payload.model_copy(
                    update={
                        "active_medications": [
                            summary_item(
                                source_type=TimelineSourceType.MEDICATION.value,
                                source_id=row.id,
                                code_system=row.code_system,
                                code=row.code,
                                code_display=row.code_display,
                                status=row.status,
                                occurred_at=row_occurred_at(row, TimelineSourceType.MEDICATION),
                            )
                            for row in medication_rows
                        ]
                    }
                )
        if Permission.CLINICAL_ALLERGY_READ in context.scopes:
            allergy_rows = await self._queries.summary_allergies(
                org, cluster, limit=SUMMARY_ALLERGY_LIMIT, **scope
            )
            if allergy_rows:
                payload = payload.model_copy(
                    update={
                        "active_allergies": [
                            summary_item(
                                source_type=TimelineSourceType.ALLERGY.value,
                                source_id=row.id,
                                code_system=row.code_system,
                                code=row.code,
                                code_display=row.code_display,
                                status=row.clinical_status,
                                occurred_at=row_occurred_at(row, TimelineSourceType.ALLERGY),
                            )
                            for row in allergy_rows
                        ]
                    }
                )
        if Permission.CLINICAL_OBSERVATION_READ in context.scopes:
            vital_rows = await self._queries.summary_vitals(
                org, cluster, limit=SUMMARY_VITAL_LIMIT, **scope
            )
            if vital_rows:
                payload = payload.model_copy(
                    update={
                        "recent_vitals": [
                            summary_item(
                                source_type=TimelineSourceType.OBSERVATION.value,
                                source_id=row.id,
                                code_system=row.code_system,
                                code=row.code,
                                code_display=row.code_display,
                                status=row.status,
                                occurred_at=row_occurred_at(row, TimelineSourceType.OBSERVATION),
                            )
                            for row in vital_rows
                        ]
                    }
                )
        if Permission.CLINICAL_LAB_RESULT_READ in context.scopes:
            lab_rows = await self._queries.summary_lab_results(
                org, cluster, limit=SUMMARY_LAB_LIMIT, **scope
            )
            if lab_rows:
                payload = payload.model_copy(
                    update={
                        "recent_lab_results": [
                            summary_item(
                                source_type=TimelineSourceType.LABORATORY_RESULT.value,
                                source_id=row.id,
                                code_system=row.code_system,
                                code=row.code,
                                code_display=row.code_display,
                                status=row.status,
                                occurred_at=row_occurred_at(
                                    row, TimelineSourceType.LABORATORY_RESULT
                                ),
                            )
                            for row in lab_rows
                        ]
                    }
                )
        if Permission.CLINICAL_PROCEDURE_READ in context.scopes:
            procedure_rows = await self._queries.summary_procedures(
                org, cluster, limit=SUMMARY_PROCEDURE_LIMIT, **scope
            )
            if procedure_rows:
                payload = payload.model_copy(
                    update={
                        "recent_procedures": [
                            summary_item(
                                source_type=TimelineSourceType.PROCEDURE.value,
                                source_id=row.id,
                                code_system=row.code_system,
                                code=row.code,
                                code_display=row.code_display,
                                status=row.status,
                                occurred_at=row_occurred_at(row, TimelineSourceType.PROCEDURE),
                            )
                            for row in procedure_rows
                        ]
                    }
                )
        await self._audit_chart_access(context, ChartSurface.SUMMARY, sections)
        return payload

    async def get_timeline(
        self,
        principal: Principal | None,
        patient_identity_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
        encounter_id: UUID | None,
        query_facility_id: UUID | None,
        cursor: ChartCursor | None,
        limit: int | None,
        recorded_from: datetime | None,
        recorded_to: datetime | None,
    ) -> TimelinePageResponse:
        context = await self._open_chart(
            principal,
            patient_identity_id,
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
            encounter_id=encounter_id,
            query_facility_id=query_facility_id,
        )
        page_size = parse_limit(limit)
        fact_query = FactQuery(
            organization_id=context.organization_id,
            cluster_ids=context.cluster_ids,
            encounter_id=encounter_id,
            facility_id=query_facility_id,
            recorded_from=recorded_from,
            recorded_to=recorded_to,
            cursor=cursor,
            limit=page_size,
        )
        merged: list[tuple[datetime, TimelineSourceType, UUID, TimelineItemDTO]] = []
        for source_type, permission in SOURCE_PERMISSION.items():
            if permission not in context.scopes:
                continue
            rows = await self._queries.page_source(source_type, fact_query)
            for row in rows:
                item = timeline_item(
                    row,
                    source_type,
                    canonical_patient_identity_id=context.canonical.id,
                )
                merged.append((item.occurred_at, source_type, row.id, item))
        items, has_more, next_cursor = paginate_timeline(merged, limit=page_size, cursor=cursor)
        sections = authorized_sections(context.scopes)
        await self._audit_chart_access(context, ChartSurface.TIMELINE, sections)
        encoded = None if next_cursor is None else encode_cursor(next_cursor)
        return TimelinePageResponse(
            requested_patient_identity_id=context.requested_id,
            canonical_patient_identity_id=context.canonical.id,
            items=items,
            has_more=has_more,
            next_cursor=encoded,
        )

    async def get_section(
        self,
        principal: Principal | None,
        patient_identity_id: UUID,
        section: ChartSection,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
        encounter_id: UUID | None,
        query_facility_id: UUID | None,
        cursor: ChartCursor | None,
        limit: int | None,
        status: str | None,
        category: str | None,
        recorded_from: datetime | None,
        recorded_to: datetime | None,
    ) -> SectionPageResponse:
        context = await self._open_chart(
            principal,
            patient_identity_id,
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
            encounter_id=encounter_id,
            query_facility_id=query_facility_id,
        )
        action = section_authorize_action(context.scopes, section)
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=action,
            resource_type="ClinicalChartSection",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=context.canonical.id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        validate_section_filters(section, status=status, category=category, scopes=context.scopes)
        page_size = parse_limit(limit)
        fact_query = FactQuery(
            organization_id=context.organization_id,
            cluster_ids=context.cluster_ids,
            encounter_id=encounter_id,
            facility_id=query_facility_id,
            status=status,
            category=category,
            recorded_from=recorded_from,
            recorded_to=recorded_to,
            cursor=cursor,
            limit=page_size,
        )
        items, has_more, next_cursor = await self._project_section(
            context, section, fact_query, page_size
        )
        encoded = None if next_cursor is None else encode_cursor(next_cursor)
        return SectionPageResponse(
            requested_patient_identity_id=context.requested_id,
            canonical_patient_identity_id=context.canonical.id,
            section=section,
            items=items,
            has_more=has_more,
            next_cursor=encoded,
        )

    async def _open_chart(
        self,
        principal: Principal | None,
        patient_identity_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
        encounter_id: UUID | None,
        query_facility_id: UUID | None,
    ) -> ChartContext:
        if purpose == Purpose.PATIENT_ACCESS:
            raise AppError(
                "purpose_principal_mismatch",
                "PATIENT_ACCESS is not valid for staff chart routes",
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
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._mpi.get_identity(patient_identity_id)
        if identity is None or not await self._identity_visible(identity, organization_id):
            raise NotFoundError("Patient identity not found")
        if IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.RETIRED:
            raise AppError(
                "identity_not_usable",
                "A retired identity cannot receive clinical records",
                status_code=409,
            )
        canonical = await self._mpi.resolve_canonical_identity(patient_identity_id)
        if canonical is None:
            raise AppError(
                "canonical_resolution_failed",
                "Identity cannot be resolved to a canonical active identity",
                status_code=409,
            )
        cluster_ids = tuple(await self._mpi.list_cluster_identity_ids(canonical.id))
        if query_facility_id is not None:
            await self._require_facility_filter(principal, query_facility_id, organization_id)
        context = ChartContext(
            requested_id=patient_identity_id,
            canonical=canonical,
            cluster_ids=cluster_ids,
            organization_id=organization_id,
            header_facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
            principal=principal,
            scopes=frozenset() if principal is None else principal.permission_codes,
        )
        if encounter_id is not None:
            encounter = await self._queries.get_encounter(
                encounter_id, organization_id, cluster_ids
            )
            if encounter is None:
                raise NotFoundError("Encounter not found")
        return context

    async def _identity_visible(
        self, identity: PatientIdentityModel, organization_id: UUID
    ) -> bool:
        provenances = await self._mpi.list_provenances(identity.id)
        if any(item.source_organization_id == organization_id for item in provenances):
            return True
        identifiers = await self._mpi.list_identifiers(identity.id)
        return any(item.organization_id == organization_id for item in identifiers)

    async def _require_facility_filter(
        self,
        principal: Principal | None,
        facility_id: UUID,
        organization_id: UUID,
    ) -> None:
        facility = await self._organizations.get_facility(facility_id)
        if facility is None or facility.organization_id != organization_id:
            raise NotFoundError("Resource not found")
        if principal is not None and principal.facility_ids:
            if facility_id not in principal.facility_ids:
                raise NotFoundError("Resource not found")

    async def _header(
        self, context: ChartContext, *, encounter_id: UUID | None
    ) -> PatientHeaderDTO:
        identity = context.canonical
        as_of = datetime.now(UTC).date()
        age = None if identity.birth_date is None else age_years(identity.birth_date, as_of)
        identifiers = await self._queries.list_identifier_rows(context.cluster_ids)
        mrns = self._queries.org_mrns(identifiers, context.organization_id)
        selected = None
        if encounter_id is not None and Permission.CLINICAL_ENCOUNTER_READ in context.scopes:
            encounter = await self._queries.get_encounter(
                encounter_id, context.organization_id, context.cluster_ids
            )
            if encounter is not None:
                selected = selected_encounter_dto(encounter)
        allergy_exists = None
        if Permission.CLINICAL_ALLERGY_READ in context.scopes:
            allergy_exists = await self._queries.documented_allergy_exists(
                context.organization_id, context.cluster_ids
            )
        return PatientHeaderDTO(
            requested_patient_identity_id=context.requested_id,
            canonical_patient_identity_id=identity.id,
            lifecycle_status=identity.lifecycle_status,
            identity_kind=identity.identity_kind,
            display_label=identity.display_label,
            given_name=identity.given_name,
            family_name=identity.family_name,
            birth_date=identity.birth_date,
            age_years=age,
            administrative_sex=identity.administrative_sex,
            mrn=mrns,
            selected_encounter=selected,
            documented_allergy_exists=allergy_exists,
        )

    async def _project_section(
        self,
        context: ChartContext,
        section: ChartSection,
        query: FactQuery,
        page_size: int,
    ) -> tuple[list[dict[str, object]], bool, ChartCursor | None]:
        if section is ChartSection.LABORATORY:
            return await self._project_laboratory(context, query, page_size)
        source_type = _SECTION_SOURCE[section]
        rows = await self._queries.page_source(source_type, query)
        projector = _SECTION_PROJECTOR[section]
        has_more = len(rows) > page_size
        page = rows[:page_size]
        items = [dump_dto(projector(row)) for row in page]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = ChartCursor(
                occurred_at=row_occurred_at(last, source_type),
                source_type=source_type.value,
                source_id=last.id,
            )
        return items, has_more, next_cursor

    async def _project_laboratory(
        self,
        context: ChartContext,
        query: FactQuery,
        page_size: int,
    ) -> tuple[list[dict[str, object]], bool, ChartCursor | None]:
        scopes = context.scopes
        can_order = Permission.CLINICAL_LAB_ORDER_READ in scopes
        can_specimen = Permission.CLINICAL_LAB_SPECIMEN_READ in scopes
        can_result = Permission.CLINICAL_LAB_RESULT_READ in scopes
        if can_order:
            source = TimelineSourceType.LABORATORY_ORDER
            rows = await self._queries.page_source(source, query)
            has_more = len(rows) > page_size
            page = rows[:page_size]
            specimens, results = await self._queries.list_lab_children(
                order_ids=[row.id for row in page],
                organization_id=context.organization_id,
                cluster_ids=context.cluster_ids,
                include_specimens=can_specimen,
                include_results=can_result,
            )
            specimens_by_order: dict[UUID, list[LaboratorySpecimenModel]] = {}
            results_by_order: dict[UUID, list[LaboratoryResultModel]] = {}
            if can_specimen:
                for specimen in specimens:
                    specimens_by_order.setdefault(specimen.laboratory_order_id, []).append(specimen)
            if can_result:
                for result in results:
                    results_by_order.setdefault(result.laboratory_order_id, []).append(result)
            items = [
                dump_dto(
                    lab_order_dto(
                        row,
                        specimens=specimens_by_order.get(row.id, []) if can_specimen else None,
                        results=results_by_order.get(row.id, []) if can_result else None,
                    )
                )
                for row in page
            ]
        elif can_specimen:
            source = TimelineSourceType.LABORATORY_SPECIMEN
            rows = await self._queries.page_source(source, query)
            has_more = len(rows) > page_size
            page = rows[:page_size]
            items = [dump_dto(lab_specimen_dto(row)) for row in page]
        else:
            source = TimelineSourceType.LABORATORY_RESULT
            rows = await self._queries.page_source(source, query)
            has_more = len(rows) > page_size
            page = rows[:page_size]
            items = [dump_dto(lab_result_dto(row)) for row in page]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = ChartCursor(
                occurred_at=row_occurred_at(last, source),
                source_type=source.value,
                source_id=last.id,
            )
        return items, has_more, next_cursor

    async def _audit_chart_access(
        self,
        context: ChartContext,
        surface: ChartSurface,
        sections: tuple[ChartSection, ...],
    ) -> None:
        metadata = {
            "purpose": context.purpose,
            "canonical_patient_identity_id": str(context.canonical.id),
            "surface": surface.value,
            "authorized_sections": ",".join(section.value for section in sections),
        }
        if context.requested_id != context.canonical.id:
            metadata["requested_patient_identity_id"] = str(context.requested_id)
        actor_id = None if context.principal is None else context.principal.user.id
        await self._audit.record(
            AuditEvent(
                action=ClinicalReadAuditAction.CLINICAL_CHART_ACCESSED.value,
                resource_type="ClinicalChart",
                result=AuditResult.SUCCESS,
                actor_id=actor_id,
                organization_id=context.organization_id,
                facility_id=context.header_facility_id,
                resource_id=context.canonical.id,
                patient_id=context.canonical.id,
                purpose=context.purpose,
                correlation_id=context.correlation_id,
                metadata=metadata,
            )
        )


_SECTION_SOURCE: dict[ChartSection, TimelineSourceType] = {
    ChartSection.ENCOUNTERS: TimelineSourceType.ENCOUNTER,
    ChartSection.NOTES: TimelineSourceType.NOTE,
    ChartSection.CONDITIONS: TimelineSourceType.CONDITION,
    ChartSection.OBSERVATIONS: TimelineSourceType.OBSERVATION,
    ChartSection.MEDICATIONS: TimelineSourceType.MEDICATION,
    ChartSection.ALLERGIES: TimelineSourceType.ALLERGY,
    ChartSection.CONSENTS: TimelineSourceType.CONSENT,
    ChartSection.IMMUNIZATIONS: TimelineSourceType.IMMUNIZATION,
    ChartSection.PROCEDURES: TimelineSourceType.PROCEDURE,
    ChartSection.MEDICAL_DEVICES: TimelineSourceType.MEDICAL_DEVICE,
    ChartSection.ADVERSE_EVENTS: TimelineSourceType.ADVERSE_EVENT,
    ChartSection.FAMILY_HISTORIES: TimelineSourceType.FAMILY_HISTORY,
}

_SECTION_PROJECTOR: dict[ChartSection, Callable[[Any], BaseModel]] = {
    ChartSection.ENCOUNTERS: encounter_dto,
    ChartSection.NOTES: note_list_dto,
    ChartSection.CONDITIONS: condition_dto,
    ChartSection.OBSERVATIONS: observation_dto,
    ChartSection.MEDICATIONS: medication_dto,
    ChartSection.ALLERGIES: allergy_dto,
    ChartSection.CONSENTS: consent_dto,
    ChartSection.IMMUNIZATIONS: immunization_dto,
    ChartSection.PROCEDURES: procedure_dto,
    ChartSection.MEDICAL_DEVICES: medical_device_dto,
    ChartSection.ADVERSE_EVENTS: adverse_event_dto,
    ChartSection.FAMILY_HISTORIES: family_history_dto,
}
