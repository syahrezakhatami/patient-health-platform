from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.audit.application.ports import AuditSink
from app.modules.audit.domain.events import AuditEvent
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.catalog import PATIENT_PERMISSIONS, Permission
from app.modules.authorization.domain.purpose import Purpose
from app.modules.mpi.domain.canonical import MAX_SURVIVOR_HOPS
from app.modules.mpi.domain.enums import IdentityLifecycle
from app.modules.mpi.infrastructure.repositories import MpiRepository
from app.modules.organization.infrastructure.repositories import OrganizationRepository
from app.modules.patient_access.domain.enums import PatientAccountStatus
from app.modules.patient_access.domain.models import PatientAccount, PatientPrincipal
from app.modules.patient_access.infrastructure.models import PatientAccountModel
from app.modules.patient_access.infrastructure.repositories import PatientAccountRepository
from app.shared.enums import AuditResult
from app.shared.types.ids import new_id


class PatientAccessService:
    def __init__(
        self,
        session: AsyncSession,
        pdp: PolicyDecisionPoint,
        audit: AuditSink,
    ) -> None:
        self._session = session
        self._pdp = pdp
        self._audit = audit
        self._accounts = PatientAccountRepository(session)
        self._mpi = MpiRepository(session)
        self._orgs = OrganizationRepository(session)

    async def bind_account(
        self,
        *,
        subject: str,
        patient_identity_id: UUID,
        organization_id: UUID | None,
        correlation_id: str | None,
    ) -> PatientAccount:
        existing = await self._accounts.get_by_subject(subject)
        if existing is not None:
            raise ConflictError("A patient account with this subject already exists")
        identity = await self._mpi.get_identity_for_update(patient_identity_id)
        if identity is None:
            raise NotFoundError("Resource not found")
        status = IdentityLifecycle(identity.lifecycle_status)
        if status is IdentityLifecycle.ANONYMOUS:
            raise AppError(
                "identity_not_eligible",
                "Anonymous identities cannot bind a patient account",
                status_code=409,
            )
        if status is IdentityLifecycle.RETIRED:
            raise AppError(
                "identity_not_eligible",
                "Retired identities cannot bind a patient account",
                status_code=409,
            )
        if status is IdentityLifecycle.MERGED:
            raise AppError(
                "identity_not_eligible",
                "Merged identities cannot bind a patient account",
                status_code=409,
            )
        if status is not IdentityLifecycle.ACTIVE:
            raise AppError(
                "identity_not_eligible",
                "Identity is not eligible for a patient account",
                status_code=409,
            )
        duplicate = await self._accounts.get_active_model_by_identity_for_update(
            patient_identity_id
        )
        if duplicate is not None:
            raise ConflictError("Patient identity is already bound")
        model = PatientAccountModel(
            id=new_id(),
            subject=subject.strip(),
            patient_identity_id=patient_identity_id,
            status=PatientAccountStatus.ACTIVE,
        )
        try:
            await self._accounts.add(model)
        except IntegrityError as exc:
            raise ConflictError("Patient account binding already exists") from exc
        await self._audit.record(
            AuditEvent(
                action="PATIENT_ACCOUNT_BOUND",
                resource_type="PatientAccount",
                result=AuditResult.SUCCESS,
                organization_id=organization_id,
                resource_id=model.id,
                patient_id=patient_identity_id,
                purpose=Purpose.PATIENT_ACCESS.value,
                correlation_id=correlation_id,
            )
        )
        account = await self._accounts.get(model.id)
        if account is None:
            raise NotFoundError("Resource not found")
        return account

    async def resolve_principal(self, subject: str) -> PatientPrincipal | None:
        model = await self._accounts.get_model_by_subject_for_update(subject)
        if model is None or model.status != PatientAccountStatus.ACTIVE:
            return None
        await self._mpi.get_identity_for_update(model.patient_identity_id)
        canonical_id, cluster_ids = await self._resolve_canonical_and_cluster(
            model.patient_identity_id
        )
        if canonical_id is None:
            await self._disable(model.id, "RETIRED")
            await self._session.commit()
            return None
        if canonical_id != model.patient_identity_id:
            occupant = await self._accounts.get_active_model_by_identity_for_update(canonical_id)
            if occupant is not None and occupant.id != model.id:
                first, second = sorted((model.id, occupant.id))
                await self._accounts.get_model_for_update(first)
                await self._accounts.get_model_for_update(second)
                await self._disable(model.id, "COLLISION")
                await self._disable(occupant.id, "COLLISION")
                await self._session.commit()
                return None
            model.patient_identity_id = canonical_id
            await self._session.flush()
        account = PatientAccount(
            id=model.id,
            subject=model.subject,
            patient_identity_id=model.patient_identity_id,
            status=PatientAccountStatus(model.status),
            created_at=model.created_at,
        )
        return PatientPrincipal(
            account=account,
            canonical_patient_identity_id=canonical_id,
            cluster_identity_ids=frozenset(cluster_ids),
            permission_codes=PATIENT_PERMISSIONS,
        )

    async def read_account(
        self,
        principal: PatientPrincipal,
        *,
        organization_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> dict[str, object]:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.PATIENT_ACCOUNT_READ,
            resource_type="PatientAccount",
            organization_id=organization_id,
            patient_id=principal.canonical_patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        return {
            "id": str(principal.account.id),
            "subject": principal.account.subject,
            "patient_identity_id": str(principal.account.patient_identity_id),
            "canonical_patient_identity_id": str(principal.canonical_patient_identity_id),
            "status": principal.account.status.value,
        }

    async def authorize_record_access(
        self,
        principal: PatientPrincipal,
        *,
        requested_patient_identity_id: UUID,
        organization_id: UUID,
        purpose: str,
        correlation_id: str | None,
    ) -> dict[str, object]:
        organization = await self._orgs.get_organization(organization_id)
        if organization is None:
            raise NotFoundError("Resource not found")
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.PATIENT_RECORD_READ,
            resource_type="PatientRecord",
            organization_id=organization_id,
            patient_id=requested_patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        visible_ids = principal.cluster_identity_ids | {principal.canonical_patient_identity_id}
        if not await self._visible_in_organization(visible_ids, organization_id):
            raise NotFoundError("Resource not found")
        return {
            "canonical_patient_identity_id": str(principal.canonical_patient_identity_id),
            "cluster_identity_ids": sorted(str(item) for item in principal.cluster_identity_ids),
            "organization_id": str(organization_id),
        }

    async def _resolve_canonical_and_cluster(
        self, bound_identity_id: UUID
    ) -> tuple[UUID | None, tuple[UUID, ...]]:
        current = bound_identity_id
        seen: set[UUID] = set()
        for _ in range(MAX_SURVIVOR_HOPS):
            if current in seen:
                return None, ()
            seen.add(current)
            row = await self._mpi.get_identity(current)
            if row is None:
                return None, ()
            status = IdentityLifecycle(row.lifecycle_status)
            if status is IdentityLifecycle.RETIRED:
                return None, ()
            if status is IdentityLifecycle.MERGED:
                nxt = row.surviving_identity_id
                if nxt is None or nxt == current:
                    return None, ()
                current = nxt
                continue
            cluster_ids = await self._mpi.list_cluster_identity_ids(current)
            return current, tuple(cluster_ids)
        return None, ()

    async def _visible_in_organization(
        self, identity_ids: frozenset[UUID], organization_id: UUID
    ) -> bool:
        for identity_id in identity_ids:
            provenances = await self._mpi.list_provenances(identity_id)
            if any(item.source_organization_id == organization_id for item in provenances):
                return True
            identifiers = await self._mpi.list_identifiers(identity_id)
            if any(item.organization_id == organization_id for item in identifiers):
                return True
        return False

    async def _disable(self, account_id: UUID, reason: str) -> None:
        model = await self._accounts.get_model(account_id)
        if model is None:
            return
        model.status = PatientAccountStatus.DISABLED
        await self._session.flush()
        await self._audit.record(
            AuditEvent(
                action="PATIENT_ACCOUNT_DISABLED",
                resource_type="PatientAccount",
                result=AuditResult.SUCCESS,
                resource_id=account_id,
                patient_id=model.patient_identity_id,
                purpose=Purpose.PATIENT_ACCESS.value,
                metadata={"reason": reason},
            )
        )
