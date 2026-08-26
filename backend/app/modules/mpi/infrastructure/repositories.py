from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mpi.domain.canonical import MAX_SURVIVOR_HOPS, resolve_canonical_id
from app.modules.mpi.domain.enums import (
    ClusterMembershipStatus,
    IdentifierType,
    IdentifierVerificationStatus,
    IdentityKind,
    IdentityLifecycle,
    MergeOperationStatus,
    MergeOperationType,
)
from app.modules.mpi.domain.matching import IdentifierProbe, StoredIdentity
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


class MpiRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_identity(self, model: PatientIdentityModel) -> PatientIdentityModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_identifier(self, model: PatientIdentifierModel) -> PatientIdentifierModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_cluster(self, model: IdentityClusterModel) -> IdentityClusterModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_cluster_member(
        self, model: IdentityClusterMemberModel
    ) -> IdentityClusterMemberModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_provenance(self, model: IdentityProvenanceModel) -> IdentityProvenanceModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_match_candidate(
        self, model: IdentityMatchCandidateModel
    ) -> IdentityMatchCandidateModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_match_probe(self, model: IdentityMatchProbeModel) -> IdentityMatchProbeModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_merge_operation(
        self, model: IdentityMergeOperationModel
    ) -> IdentityMergeOperationModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_identity(self, identity_id: UUID) -> PatientIdentityModel | None:
        return await self._session.get(PatientIdentityModel, identity_id)

    async def get_identity_for_update(self, identity_id: UUID) -> PatientIdentityModel | None:
        result = await self._session.execute(
            select(PatientIdentityModel)
            .where(PatientIdentityModel.id == identity_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_identifier(self, identifier_id: UUID) -> PatientIdentifierModel | None:
        return await self._session.get(PatientIdentifierModel, identifier_id)

    async def get_match_candidate(self, candidate_id: UUID) -> IdentityMatchCandidateModel | None:
        return await self._session.get(IdentityMatchCandidateModel, candidate_id)

    async def get_merge_operation(self, operation_id: UUID) -> IdentityMergeOperationModel | None:
        return await self._session.get(IdentityMergeOperationModel, operation_id)

    async def get_merge_by_idempotency_key(
        self, idempotency_key: str
    ) -> IdentityMergeOperationModel | None:
        result = await self._session.execute(
            select(IdentityMergeOperationModel).where(
                IdentityMergeOperationModel.idempotency_key == idempotency_key
            )
        )
        return result.scalar_one_or_none()

    async def get_completed_merge(
        self, source_id: UUID, target_id: UUID
    ) -> IdentityMergeOperationModel | None:
        result = await self._session.execute(
            select(IdentityMergeOperationModel).where(
                IdentityMergeOperationModel.source_identity_id == source_id,
                IdentityMergeOperationModel.target_identity_id == target_id,
                IdentityMergeOperationModel.operation == MergeOperationType.MERGE,
                IdentityMergeOperationModel.status == MergeOperationStatus.COMPLETED,
            )
        )
        return result.scalars().first()

    async def list_identifiers(self, identity_id: UUID) -> list[PatientIdentifierModel]:
        result = await self._session.execute(
            select(PatientIdentifierModel).where(
                PatientIdentifierModel.patient_identity_id == identity_id
            )
        )
        return list(result.scalars().all())

    async def find_active_identifier(
        self,
        identifier_system: str,
        normalized_value: str,
        organization_id: UUID | None,
    ) -> PatientIdentifierModel | None:
        stmt = select(PatientIdentifierModel).where(
            PatientIdentifierModel.identifier_system == identifier_system,
            PatientIdentifierModel.normalized_value == normalized_value,
            PatientIdentifierModel.valid_to.is_(None),
            PatientIdentifierModel.verification_status.notin_(
                [
                    IdentifierVerificationStatus.REJECTED,
                    IdentifierVerificationStatus.EXPIRED,
                ]
            ),
        )
        if organization_id is None:
            stmt = stmt.where(PatientIdentifierModel.organization_id.is_(None))
        else:
            stmt = stmt.where(PatientIdentifierModel.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_match_pair(
        self, left_id: UUID, right_id: UUID
    ) -> IdentityMatchCandidateModel | None:
        result = await self._session.execute(
            select(IdentityMatchCandidateModel).where(
                IdentityMatchCandidateModel.left_identity_id == left_id,
                IdentityMatchCandidateModel.right_identity_id == right_id,
            )
        )
        return result.scalar_one_or_none()

    async def active_cluster_member(self, identity_id: UUID) -> IdentityClusterMemberModel | None:
        result = await self._session.execute(
            select(IdentityClusterMemberModel).where(
                IdentityClusterMemberModel.identity_id == identity_id,
                IdentityClusterMemberModel.valid_to.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_cluster_identity_ids(self, canonical_identity_id: UUID) -> list[UUID]:
        member = await self.active_cluster_member(canonical_identity_id)
        if member is None:
            return [canonical_identity_id]
        result = await self._session.execute(
            select(IdentityClusterMemberModel.identity_id).where(
                IdentityClusterMemberModel.cluster_id == member.cluster_id,
                IdentityClusterMemberModel.membership_status.in_(
                    (
                        ClusterMembershipStatus.ACTIVE,
                        ClusterMembershipStatus.MERGED_IN,
                    )
                ),
            )
        )
        found = list(result.scalars().all())
        if canonical_identity_id not in found:
            found.append(canonical_identity_id)
        return found

    async def list_match_candidates_for_probe(
        self,
        *,
        name_normalized: str | None,
        birth_date: object | None,
        identifier_keys: list[tuple[str, str, UUID | None]],
    ) -> list[StoredIdentity]:
        identity_ids: set[UUID] = set()
        if identifier_keys:
            conditions = []
            for system, normalized, organization_id in identifier_keys:
                condition = (
                    (PatientIdentifierModel.identifier_system == system)
                    & (PatientIdentifierModel.normalized_value == normalized)
                    & PatientIdentifierModel.valid_to.is_(None)
                )
                if organization_id is None:
                    condition = condition & PatientIdentifierModel.organization_id.is_(None)
                else:
                    condition = condition & (
                        PatientIdentifierModel.organization_id == organization_id
                    )
                conditions.append(condition)
            ident_result = await self._session.execute(
                select(PatientIdentifierModel.patient_identity_id).where(or_(*conditions))
            )
            identity_ids.update(ident_result.scalars().all())
        if name_normalized and birth_date is not None:
            demo_result = await self._session.execute(
                select(PatientIdentityModel.id).where(
                    PatientIdentityModel.name_normalized == name_normalized,
                    PatientIdentityModel.birth_date == birth_date,
                    PatientIdentityModel.lifecycle_status != IdentityLifecycle.RETIRED,
                )
            )
            identity_ids.update(demo_result.scalars().all())
        if not identity_ids:
            return []
        return await self.load_canonical_stored_identities(list(identity_ids))

    async def resolve_canonical_identity(self, identity_id: UUID) -> PatientIdentityModel | None:
        cache: dict[UUID, PatientIdentityModel] = {}
        current = identity_id
        for _ in range(MAX_SURVIVOR_HOPS):
            if current not in cache:
                loaded = await self.get_identity(current)
                if loaded is None:
                    return None
                cache[current] = loaded
            resolved = resolve_canonical_id(
                identity_id,
                status_of=lambda item: (
                    IdentityLifecycle(cache[item].lifecycle_status) if item in cache else None
                ),
                surviving_of=lambda item: (
                    cache[item].surviving_identity_id if item in cache else None
                ),
            )
            if resolved is not None:
                return cache.get(resolved) or await self.get_identity(resolved)
            row = cache[current]
            if IdentityLifecycle(row.lifecycle_status) is not IdentityLifecycle.MERGED:
                return None
            if row.surviving_identity_id is None or row.surviving_identity_id in cache:
                return None
            current = row.surviving_identity_id
        return None

    async def load_canonical_stored_identities(
        self, identity_ids: list[UUID]
    ) -> list[StoredIdentity]:
        by_canonical: dict[UUID, StoredIdentity] = {}
        for raw_id in identity_ids:
            raw = await self.get_identity(raw_id)
            if raw is None:
                continue
            canonical = await self.resolve_canonical_identity(raw_id)
            if canonical is None:
                continue
            raw_ids = await self.list_identifiers(raw.id)
            canonical_ids = await self.list_identifiers(canonical.id)
            merged_identifiers = tuple(_model_to_probe(item) for item in [*raw_ids, *canonical_ids])
            existing = by_canonical.get(canonical.id)
            if existing is None:
                by_canonical[canonical.id] = StoredIdentity(
                    identity_id=canonical.id,
                    lifecycle_status=IdentityLifecycle(canonical.lifecycle_status),
                    name_normalized=canonical.name_normalized or raw.name_normalized,
                    birth_date=canonical.birth_date or raw.birth_date,
                    identifiers=merged_identifiers,
                )
            else:
                by_canonical[canonical.id] = StoredIdentity(
                    identity_id=existing.identity_id,
                    lifecycle_status=existing.lifecycle_status,
                    name_normalized=existing.name_normalized,
                    birth_date=existing.birth_date,
                    identifiers=existing.identifiers + merged_identifiers,
                )
        return list(by_canonical.values())

    async def load_stored_identities(self, identity_ids: list[UUID]) -> list[StoredIdentity]:
        if not identity_ids:
            return []
        identities = await self._session.execute(
            select(PatientIdentityModel).where(PatientIdentityModel.id.in_(identity_ids))
        )
        identifiers = await self._session.execute(
            select(PatientIdentifierModel).where(
                PatientIdentifierModel.patient_identity_id.in_(identity_ids)
            )
        )
        by_identity: dict[UUID, list[IdentifierProbe]] = {item: [] for item in identity_ids}
        for row in identifiers.scalars().all():
            by_identity.setdefault(row.patient_identity_id, []).append(
                IdentifierProbe(
                    identifier_system=row.identifier_system,
                    identifier_type=IdentifierType(row.identifier_type),
                    normalized_value=row.normalized_value,
                    organization_id=row.organization_id,
                    verification_status=IdentifierVerificationStatus(row.verification_status),
                )
            )
        stored: list[StoredIdentity] = []
        for identity in identities.scalars().all():
            stored.append(
                StoredIdentity(
                    identity_id=identity.id,
                    lifecycle_status=IdentityLifecycle(identity.lifecycle_status),
                    name_normalized=identity.name_normalized,
                    birth_date=identity.birth_date,
                    identifiers=tuple(by_identity.get(identity.id, [])),
                )
            )
        return stored

    async def count_authoritative_by_identifier(
        self,
        identifier_system: str,
        normalized_value: str,
        organization_id: UUID | None,
    ) -> int:
        identifier = await self.find_active_identifier(
            identifier_system, normalized_value, organization_id
        )
        if identifier is None:
            return 0
        identity = await self.get_identity(identifier.patient_identity_id)
        if identity is None:
            return 0
        if identity.lifecycle_status in {
            IdentityLifecycle.ACTIVE,
            IdentityLifecycle.ANONYMOUS,
        }:
            return 1
        return 0

    async def list_provenances(self, subject_id: UUID) -> list[IdentityProvenanceModel]:
        result = await self._session.execute(
            select(IdentityProvenanceModel).where(IdentityProvenanceModel.subject_id == subject_id)
        )
        return list(result.scalars().all())

    async def list_merge_operations_for_identity(
        self, identity_id: UUID
    ) -> list[IdentityMergeOperationModel]:
        result = await self._session.execute(
            select(IdentityMergeOperationModel).where(
                or_(
                    IdentityMergeOperationModel.source_identity_id == identity_id,
                    IdentityMergeOperationModel.target_identity_id == identity_id,
                )
            )
        )
        return list(result.scalars().all())


def utc_now() -> datetime:
    return datetime.now(UTC)


def identity_kind_for(status: IdentityLifecycle) -> IdentityKind:
    if status is IdentityLifecycle.ANONYMOUS:
        return IdentityKind.ANONYMOUS
    return IdentityKind.STANDARD


def _model_to_probe(model: PatientIdentifierModel) -> IdentifierProbe:
    return IdentifierProbe(
        identifier_system=model.identifier_system,
        identifier_type=IdentifierType(model.identifier_type),
        normalized_value=model.normalized_value,
        organization_id=model.organization_id,
        verification_status=IdentifierVerificationStatus(model.verification_status),
    )
