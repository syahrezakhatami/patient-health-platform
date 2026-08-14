from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.audit.application.ports import AuditSink
from app.modules.audit.domain.events import AuditEvent
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.catalog import Permission
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.domain.models import OrganizationMembership, Principal, User
from app.modules.iam.infrastructure.models import OrganizationMembershipModel, UserModel
from app.modules.iam.infrastructure.repositories import IamRepository
from app.modules.organization.infrastructure.repositories import OrganizationRepository
from app.shared.enums import AuditResult
from app.shared.types.ids import new_id


class IamService:
    def __init__(
        self,
        session: AsyncSession,
        pdp: PolicyDecisionPoint,
        audit: AuditSink,
    ) -> None:
        self._session = session
        self._pdp = pdp
        self._audit = audit
        self._iam = IamRepository(session)
        self._orgs = OrganizationRepository(session)

    async def provision_user(
        self,
        principal: Principal | None,
        *,
        subject: str,
        display_name: str,
        organization_id: UUID | None,
        correlation_id: str | None,
    ) -> User:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.IAM_USER_PROVISION,
            resource_type="User",
            organization_id=organization_id,
            purpose="iam_administration",
            correlation_id=correlation_id,
        )
        existing = await self._iam.get_user_by_subject(subject)
        if existing is not None:
            raise ConflictError("A user with this subject already exists")
        model = UserModel(
            id=new_id(),
            subject=subject.strip(),
            display_name=display_name.strip(),
            status=UserStatus.ACTIVE,
        )
        try:
            await self._iam.add_user(model)
        except IntegrityError as exc:
            raise ConflictError("A user with this subject already exists") from exc
        user = User(
            id=model.id,
            subject=model.subject,
            display_name=model.display_name,
            status=UserStatus(model.status),
            created_at=model.created_at,
        )
        await self._audit.record(
            AuditEvent(
                action="IAM_USER_PROVISIONED",
                resource_type="User",
                result=AuditResult.SUCCESS,
                actor_id=None if principal is None else principal.user.id,
                organization_id=organization_id,
                resource_id=user.id,
                purpose="iam_administration",
                correlation_id=correlation_id,
            )
        )
        return user

    async def assign_membership(
        self,
        principal: Principal | None,
        *,
        user_id: UUID,
        organization_id: UUID | None,
        facility_id: UUID | None,
        role_code: str,
        actor_organization_id: UUID | None,
        correlation_id: str | None,
    ) -> OrganizationMembership:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.IAM_MEMBERSHIP_MANAGE,
            resource_type="OrganizationMembership",
            organization_id=organization_id or actor_organization_id,
            facility_id=facility_id,
            purpose="iam_administration",
            correlation_id=correlation_id,
        )
        user = await self._iam.get_user(user_id)
        if user is None:
            raise NotFoundError("User not found")
        role = await self._iam.get_role_by_code(role_code)
        if role is None:
            raise AppError("invalid_role", "Unknown role", status_code=422)
        if organization_id is not None:
            organization = await self._orgs.get_organization(organization_id)
            if organization is None:
                raise NotFoundError("Organization not found")
        if facility_id is not None:
            facility = await self._orgs.get_facility(facility_id)
            if facility is None:
                raise NotFoundError("Facility not found")
            if organization_id is not None and facility.organization_id != organization_id:
                raise AppError(
                    "invalid_facility",
                    "Facility does not belong to the organization",
                    422,
                )
        model = OrganizationMembershipModel(
            id=new_id(),
            user_id=user_id,
            organization_id=organization_id,
            facility_id=facility_id,
            role_id=role.id,
            status=MembershipStatus.ACTIVE,
        )
        try:
            await self._iam.add_membership(model)
        except IntegrityError as exc:
            raise ConflictError("Membership already exists") from exc
        await self._audit.record(
            AuditEvent(
                action="IAM_MEMBERSHIP_ASSIGNED",
                resource_type="OrganizationMembership",
                result=AuditResult.SUCCESS,
                actor_id=None if principal is None else principal.user.id,
                organization_id=organization_id,
                facility_id=facility_id,
                resource_id=model.id,
                purpose="iam_administration",
                correlation_id=correlation_id,
                metadata={"role": role_code},
            )
        )
        return OrganizationMembership(
            id=model.id,
            user_id=model.user_id,
            organization_id=model.organization_id,
            facility_id=model.facility_id,
            role_id=model.role_id,
            role_code=role.code,
            status=MembershipStatus.ACTIVE,
        )
