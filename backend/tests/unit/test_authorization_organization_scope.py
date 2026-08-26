from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.errors import ForbiddenError
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.product_access_pdp import ProductAccessPDP
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.authorization.domain.models import AuthorizationContext, AuthorizationDecision
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.domain.models import OrganizationMembership, Principal, User
from app.modules.patient_access.domain.enums import PatientAccountStatus
from app.modules.patient_access.domain.models import PatientAccount, PatientPrincipal
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


class _CapturePDP:
    def __init__(self) -> None:
        self.seen: list[AuthorizationContext] = []
        self._inner = ProductAccessPDP()

    def evaluate(self, context: AuthorizationContext) -> AuthorizationDecision:
        self.seen.append(context)
        return self._inner.evaluate(context)


def _user() -> User:
    return User(
        id=uuid4(),
        subject="sub",
        display_name="U",
        status=UserStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )


def _membership(
    *,
    organization_id,
    role_id,
    role_code: str,
    facility_id=None,
) -> OrganizationMembership:
    return OrganizationMembership(
        id=uuid4(),
        user_id=uuid4(),
        organization_id=organization_id,
        facility_id=facility_id,
        role_id=role_id,
        role_code=role_code,
        status=MembershipStatus.ACTIVE,
    )


def _multi_org_principal() -> tuple[Principal, object, object, object, object]:
    org_a = uuid4()
    org_b = uuid4()
    a1 = uuid4()
    b2 = uuid4()
    clinician_role = uuid4()
    admin_role = uuid4()
    principal = Principal(
        user=_user(),
        memberships=(
            _membership(
                organization_id=org_a,
                role_id=clinician_role,
                role_code=RoleCode.CLINICIAN,
                facility_id=a1,
            ),
            _membership(
                organization_id=org_b,
                role_id=admin_role,
                role_code=RoleCode.ORG_ADMIN,
                facility_id=b2,
            ),
        ),
        permission_codes=frozenset(
            {Permission.CLINICAL_CONDITION_CREATE, Permission.ORG_FACILITY_CREATE}
        ),
        organization_ids=frozenset({org_a, org_b}),
        facility_ids=frozenset({a1, b2}),
        role_codes=frozenset({RoleCode.CLINICIAN, RoleCode.ORG_ADMIN}),
        permissions_by_role_id={
            clinician_role: frozenset({Permission.CLINICAL_CONDITION_CREATE}),
            admin_role: frozenset({Permission.ORG_FACILITY_CREATE}),
        },
    )
    return principal, org_a, org_b, a1, b2


@pytest.mark.asyncio
async def test_authorize_double_scope_does_not_strip_or_resurrect() -> None:
    principal, org_a, org_b, a1, b2 = _multi_org_principal()
    scoped_a = principal.for_organization(org_a)
    pdp = _CapturePDP()
    await authorize(
        pdp,
        AsyncMock(),
        session=AsyncMock(),
        principal=scoped_a,
        action=Permission.CLINICAL_CONDITION_CREATE,
        resource_type="Condition",
        organization_id=org_a,
        purpose="TREATMENT",
    )
    context = pdp.seen[0]
    assert context.principal_type is PrincipalType.STAFF
    assert Permission.CLINICAL_CONDITION_CREATE in context.scopes
    assert Permission.ORG_FACILITY_CREATE not in context.scopes
    assert context.actor_organization_ids == (org_a,)
    assert set(context.actor_facility_ids) == {a1}
    assert b2 not in context.actor_facility_ids
    with pytest.raises(ForbiddenError):
        await authorize(
            pdp,
            AsyncMock(),
            session=AsyncMock(),
            principal=scoped_a,
            action=Permission.ORG_FACILITY_CREATE,
            resource_type="Facility",
            organization_id=org_b,
            purpose="ADMINISTRATION",
        )
    mismatch = pdp.seen[1]
    assert Permission.ORG_FACILITY_CREATE not in mismatch.scopes
    assert org_b not in mismatch.actor_organization_ids


@pytest.mark.asyncio
async def test_authorize_unscoped_principal_is_projected_before_pdp() -> None:
    principal, org_a, org_b, a1, b2 = _multi_org_principal()
    pdp = _CapturePDP()
    await authorize(
        pdp,
        AsyncMock(),
        session=AsyncMock(),
        principal=principal,
        action=Permission.CLINICAL_CONDITION_CREATE,
        resource_type="Condition",
        organization_id=org_a,
        purpose="TREATMENT",
    )
    context = pdp.seen[0]
    assert Permission.CLINICAL_CONDITION_CREATE in context.scopes
    assert Permission.ORG_FACILITY_CREATE not in context.scopes
    assert set(context.actor_facility_ids) == {a1}
    assert b2 not in context.actor_facility_ids
    with pytest.raises(ForbiddenError):
        await authorize(
            pdp,
            AsyncMock(),
            session=AsyncMock(),
            principal=principal,
            action=Permission.ORG_FACILITY_CREATE,
            resource_type="Facility",
            organization_id=org_a,
            purpose="ADMINISTRATION",
        )


@pytest.mark.asyncio
async def test_authorize_none_principal_stays_denied() -> None:
    pdp = _CapturePDP()
    with pytest.raises(ForbiddenError):
        await authorize(
            pdp,
            AsyncMock(),
            session=AsyncMock(),
            principal=None,
            action=Permission.CLINICAL_CONDITION_CREATE,
            resource_type="Condition",
            organization_id=uuid4(),
            purpose="TREATMENT",
        )
    assert pdp.seen[0].actor_id is None


@pytest.mark.asyncio
async def test_authorize_does_not_project_patient_principal() -> None:
    identity = uuid4()
    account = PatientAccount(
        id=uuid4(),
        subject="patient-1",
        patient_identity_id=identity,
        status=PatientAccountStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    patient = PatientPrincipal(
        account=account,
        canonical_patient_identity_id=identity,
        cluster_identity_ids=frozenset({identity}),
        permission_codes=frozenset({Permission.PATIENT_ACCOUNT_READ}),
    )
    pdp = _CapturePDP()
    with pytest.raises(ForbiddenError):
        await authorize(
            pdp,
            AsyncMock(),
            session=AsyncMock(),
            principal=patient,
            action=Permission.CLINICAL_CONDITION_CREATE,
            resource_type="Condition",
            organization_id=uuid4(),
            purpose="PATIENT_ACCESS",
        )
    context = pdp.seen[0]
    assert context.principal_type is PrincipalType.PATIENT
    assert context.actor_organization_ids == ()
