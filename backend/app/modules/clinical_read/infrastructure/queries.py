from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import Select, and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.modules.clinical.infrastructure.models import (
    AdverseEventModel,
    AllergyModel,
    ClinicalNoteModel,
    ConditionModel,
    ConsentModel,
    EncounterModel,
    FamilyHistoryModel,
    ImmunizationModel,
    LaboratoryOrderModel,
    LaboratoryResultModel,
    LaboratorySpecimenModel,
    MedicalDeviceModel,
    MedicationModel,
    ObservationModel,
    ProcedureModel,
)
from app.modules.clinical_read.domain.catalog import TIMESTAMP_MAP
from app.modules.clinical_read.domain.cursor import ChartCursor
from app.modules.clinical_read.domain.enums import TimelineSourceType
from app.modules.mpi.domain.enums import IdentifierType
from app.modules.mpi.infrastructure.models import PatientIdentifierModel


@dataclass(frozen=True, slots=True)
class FactQuery:
    organization_id: UUID
    cluster_ids: tuple[UUID, ...]
    encounter_id: UUID | None = None
    facility_id: UUID | None = None
    status: str | None = None
    category: str | None = None
    recorded_from: datetime | None = None
    recorded_to: datetime | None = None
    cursor: ChartCursor | None = None
    limit: int = 50


class ClinicalReadQueryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_identifier_rows(
        self, identity_ids: Sequence[UUID]
    ) -> list[PatientIdentifierModel]:
        if not identity_ids:
            return []
        result = await self._session.execute(
            select(PatientIdentifierModel).where(
                PatientIdentifierModel.patient_identity_id.in_(tuple(identity_ids))
            )
        )
        return list(result.scalars().all())

    async def documented_allergy_exists(
        self, organization_id: UUID, cluster_ids: Sequence[UUID]
    ) -> bool:
        result = await self._session.execute(
            select(AllergyModel.id)
            .where(
                AllergyModel.organization_id == organization_id,
                AllergyModel.patient_identity_id.in_(tuple(cluster_ids)),
                AllergyModel.status != "ENTERED_IN_ERROR",
                AllergyModel.clinical_status == "ACTIVE",
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_encounter(
        self, encounter_id: UUID, organization_id: UUID, cluster_ids: Sequence[UUID]
    ) -> EncounterModel | None:
        result = await self._session.execute(
            select(EncounterModel).where(
                EncounterModel.id == encounter_id,
                EncounterModel.organization_id == organization_id,
                EncounterModel.patient_identity_id.in_(tuple(cluster_ids)),
            )
        )
        return result.scalar_one_or_none()

    async def page_source(
        self,
        source_type: TimelineSourceType,
        query: FactQuery,
    ) -> list[Any]:
        model = SOURCE_MODELS[source_type]
        statement = self._base_select(model, source_type, query)
        result = await self._session.execute(statement)
        rows = list(result.scalars().all())
        unique: dict[UUID, Any] = {}
        for row in rows:
            unique[row.id] = row
        return list(unique.values())

    async def list_lab_children(
        self,
        *,
        order_ids: Sequence[UUID],
        organization_id: UUID,
        cluster_ids: Sequence[UUID],
        include_specimens: bool = True,
        include_results: bool = True,
    ) -> tuple[list[LaboratorySpecimenModel], list[LaboratoryResultModel]]:
        if not order_ids:
            return [], []
        ids = tuple(order_ids)
        cluster = tuple(cluster_ids)
        specimen_rows: list[LaboratorySpecimenModel] = []
        result_rows: list[LaboratoryResultModel] = []
        if include_specimens:
            specimens = await self._session.execute(
                select(LaboratorySpecimenModel).where(
                    LaboratorySpecimenModel.laboratory_order_id.in_(ids),
                    LaboratorySpecimenModel.organization_id == organization_id,
                    LaboratorySpecimenModel.patient_identity_id.in_(cluster),
                )
            )
            specimen_rows = list(specimens.scalars().all())
        if include_results:
            results = await self._session.execute(
                select(LaboratoryResultModel).where(
                    LaboratoryResultModel.laboratory_order_id.in_(ids),
                    LaboratoryResultModel.organization_id == organization_id,
                    LaboratoryResultModel.patient_identity_id.in_(cluster),
                )
            )
            result_rows = list(results.scalars().all())
        return _unique(specimen_rows), _unique(result_rows)

    async def summary_conditions(
        self,
        organization_id: UUID,
        cluster_ids: Sequence[UUID],
        *,
        limit: int,
        encounter_id: UUID | None = None,
        facility_id: UUID | None = None,
    ) -> list[ConditionModel]:
        ts = func.coalesce(ConditionModel.onset_at, ConditionModel.recorded_at)
        statement = select(ConditionModel).where(
            ConditionModel.organization_id == organization_id,
            ConditionModel.patient_identity_id.in_(tuple(cluster_ids)),
            ConditionModel.clinical_status.in_(("ACTIVE", "RECURRENCE", "RELAPSE")),
            ConditionModel.verification_status != "ENTERED_IN_ERROR",
        )
        statement = _scope_optional(statement, ConditionModel, encounter_id, facility_id)
        result = await self._session.execute(
            statement.order_by(ts.desc(), ConditionModel.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def summary_medications(
        self,
        organization_id: UUID,
        cluster_ids: Sequence[UUID],
        *,
        limit: int,
        encounter_id: UUID | None = None,
        facility_id: UUID | None = None,
    ) -> list[MedicationModel]:
        ts = func.coalesce(MedicationModel.started_at, MedicationModel.recorded_at)
        statement = select(MedicationModel).where(
            MedicationModel.organization_id == organization_id,
            MedicationModel.patient_identity_id.in_(tuple(cluster_ids)),
            MedicationModel.status == "ACTIVE",
        )
        statement = _scope_optional(statement, MedicationModel, encounter_id, facility_id)
        result = await self._session.execute(
            statement.order_by(ts.desc(), MedicationModel.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def summary_allergies(
        self,
        organization_id: UUID,
        cluster_ids: Sequence[UUID],
        *,
        limit: int,
        encounter_id: UUID | None = None,
        facility_id: UUID | None = None,
    ) -> list[AllergyModel]:
        ts = func.coalesce(AllergyModel.onset_at, AllergyModel.recorded_at)
        statement = select(AllergyModel).where(
            AllergyModel.organization_id == organization_id,
            AllergyModel.patient_identity_id.in_(tuple(cluster_ids)),
            AllergyModel.status != "ENTERED_IN_ERROR",
            AllergyModel.clinical_status == "ACTIVE",
        )
        statement = _scope_optional(statement, AllergyModel, encounter_id, facility_id)
        result = await self._session.execute(
            statement.order_by(ts.desc(), AllergyModel.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def summary_vitals(
        self,
        organization_id: UUID,
        cluster_ids: Sequence[UUID],
        *,
        limit: int,
        encounter_id: UUID | None = None,
        facility_id: UUID | None = None,
    ) -> list[ObservationModel]:
        ts = func.coalesce(ObservationModel.effective_at, ObservationModel.recorded_at)
        statement = select(ObservationModel).where(
            ObservationModel.organization_id == organization_id,
            ObservationModel.patient_identity_id.in_(tuple(cluster_ids)),
            ObservationModel.category == "VITAL_SIGNS",
            ObservationModel.status != "ENTERED_IN_ERROR",
        )
        statement = _scope_optional(statement, ObservationModel, encounter_id, facility_id)
        result = await self._session.execute(
            statement.order_by(ts.desc(), ObservationModel.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def summary_lab_results(
        self,
        organization_id: UUID,
        cluster_ids: Sequence[UUID],
        *,
        limit: int,
        encounter_id: UUID | None = None,
        facility_id: UUID | None = None,
    ) -> list[LaboratoryResultModel]:
        ts = func.coalesce(LaboratoryResultModel.effective_at, LaboratoryResultModel.recorded_at)
        statement = select(LaboratoryResultModel).where(
            LaboratoryResultModel.organization_id == organization_id,
            LaboratoryResultModel.patient_identity_id.in_(tuple(cluster_ids)),
            LaboratoryResultModel.status != "ENTERED_IN_ERROR",
        )
        statement = _scope_optional(statement, LaboratoryResultModel, encounter_id, facility_id)
        result = await self._session.execute(
            statement.order_by(ts.desc(), LaboratoryResultModel.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def summary_procedures(
        self,
        organization_id: UUID,
        cluster_ids: Sequence[UUID],
        *,
        limit: int,
        encounter_id: UUID | None = None,
        facility_id: UUID | None = None,
    ) -> list[ProcedureModel]:
        ts = func.coalesce(ProcedureModel.occurrence_at, ProcedureModel.recorded_at)
        statement = select(ProcedureModel).where(
            ProcedureModel.organization_id == organization_id,
            ProcedureModel.patient_identity_id.in_(tuple(cluster_ids)),
            ProcedureModel.status != "ENTERED_IN_ERROR",
        )
        statement = _scope_optional(statement, ProcedureModel, encounter_id, facility_id)
        result = await self._session.execute(
            statement.order_by(ts.desc(), ProcedureModel.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    def org_mrns(
        self, identifiers: Sequence[PatientIdentifierModel], organization_id: UUID
    ) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for item in identifiers:
            if item.identifier_type != IdentifierType.MRN:
                continue
            if item.organization_id != organization_id:
                continue
            if item.identifier_value in seen:
                continue
            seen.add(item.identifier_value)
            values.append(item.identifier_value)
        return values

    def _base_select(
        self,
        model: type[Any],
        source_type: TimelineSourceType,
        query: FactQuery,
    ) -> Select[Any]:
        mapping = TIMESTAMP_MAP[source_type]
        ts = _timestamp_expr(model, mapping.primary, mapping.fallback)
        statement = select(model).where(
            model.organization_id == query.organization_id,
            model.patient_identity_id.in_(query.cluster_ids),
        )
        statement = _apply_filters(statement, model, source_type, query, ts)
        if query.cursor is not None:
            statement = statement.where(
                _after_cursor(ts, source_type.value, model.id, query.cursor)
            )
        return statement.order_by(ts.desc(), model.id.desc()).limit(query.limit + 1)


def _scope_optional(
    statement: Select[Any],
    model: type[Any],
    encounter_id: UUID | None,
    facility_id: UUID | None,
) -> Select[Any]:
    if encounter_id is not None and hasattr(model, "encounter_id"):
        statement = statement.where(model.encounter_id == encounter_id)
    if facility_id is not None and hasattr(model, "facility_id"):
        statement = statement.where(model.facility_id == facility_id)
    return statement


class _HasId(Protocol):
    id: UUID


def _unique[T: _HasId](rows: list[T]) -> list[T]:
    unique: dict[UUID, T] = {}
    for row in rows:
        unique[row.id] = row
    return list(unique.values())


def _timestamp_expr(model: type[Any], primary: str, fallback: str | None) -> ColumnElement[Any]:
    primary_col: InstrumentedAttribute[Any] = getattr(model, primary)
    if fallback is None:
        return cast(ColumnElement[Any], primary_col)
    return func.coalesce(primary_col, getattr(model, fallback))


def _after_cursor(
    ts: ColumnElement[Any],
    source_type: str,
    id_col: InstrumentedAttribute[UUID],
    cursor: ChartCursor,
) -> ColumnElement[Any]:
    return or_(
        ts < cursor.occurred_at,
        and_(ts == cursor.occurred_at, literal(source_type) > cursor.source_type),
        and_(
            ts == cursor.occurred_at,
            literal(source_type) == cursor.source_type,
            id_col < cursor.source_id,
        ),
    )


def _apply_filters(
    statement: Select[Any],
    model: type[Any],
    source_type: TimelineSourceType,
    query: FactQuery,
    ts: ColumnElement[Any],
) -> Select[Any]:
    if query.encounter_id is not None:
        if source_type is TimelineSourceType.ENCOUNTER:
            statement = statement.where(model.id == query.encounter_id)
        elif hasattr(model, "encounter_id"):
            statement = statement.where(model.encounter_id == query.encounter_id)
    if query.facility_id is not None and hasattr(model, "facility_id"):
        statement = statement.where(model.facility_id == query.facility_id)
    if query.status is not None:
        status_col = _status_column(model, source_type)
        if status_col is not None:
            statement = statement.where(status_col == query.status)
    if query.category is not None:
        if source_type is TimelineSourceType.ENCOUNTER:
            statement = statement.where(model.encounter_class == query.category)
        elif hasattr(model, "category"):
            statement = statement.where(model.category == query.category)
    if query.recorded_from is not None:
        statement = statement.where(ts >= query.recorded_from)
    if query.recorded_to is not None:
        statement = statement.where(ts <= query.recorded_to)
    return statement


def _status_column(model: type[Any], source_type: TimelineSourceType) -> Any | None:
    if source_type is TimelineSourceType.NOTE:
        return model.record_status
    if source_type is TimelineSourceType.CONDITION:
        return model.clinical_status
    if hasattr(model, "status"):
        return model.status
    return None


SOURCE_MODELS: dict[TimelineSourceType, type[Any]] = {
    TimelineSourceType.ENCOUNTER: EncounterModel,
    TimelineSourceType.NOTE: ClinicalNoteModel,
    TimelineSourceType.CONDITION: ConditionModel,
    TimelineSourceType.OBSERVATION: ObservationModel,
    TimelineSourceType.LABORATORY_ORDER: LaboratoryOrderModel,
    TimelineSourceType.LABORATORY_SPECIMEN: LaboratorySpecimenModel,
    TimelineSourceType.LABORATORY_RESULT: LaboratoryResultModel,
    TimelineSourceType.MEDICATION: MedicationModel,
    TimelineSourceType.ALLERGY: AllergyModel,
    TimelineSourceType.CONSENT: ConsentModel,
    TimelineSourceType.IMMUNIZATION: ImmunizationModel,
    TimelineSourceType.PROCEDURE: ProcedureModel,
    TimelineSourceType.MEDICAL_DEVICE: MedicalDeviceModel,
    TimelineSourceType.ADVERSE_EVENT: AdverseEventModel,
    TimelineSourceType.FAMILY_HISTORY: FamilyHistoryModel,
}
