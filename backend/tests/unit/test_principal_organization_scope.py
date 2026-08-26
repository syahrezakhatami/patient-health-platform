from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.domain.models import OrganizationMembership, Principal, User

pytestmark = pytest.mark.unit


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


def test_for_organization_excludes_other_org_permissions() -> None:
    org_a = uuid4()
    org_b = uuid4()
    clinician_role = uuid4()
    admin_role = uuid4()
    principal = Principal(
        user=_user(),
        memberships=(
            _membership(
                organization_id=org_a, role_id=clinician_role, role_code=RoleCode.CLINICIAN
            ),
            _membership(organization_id=org_b, role_id=admin_role, role_code=RoleCode.ORG_ADMIN),
        ),
        permission_codes=frozenset(
            {Permission.CLINICAL_CONDITION_CREATE, Permission.ORG_FACILITY_CREATE}
        ),
        organization_ids=frozenset({org_a, org_b}),
        facility_ids=frozenset(),
        role_codes=frozenset({RoleCode.CLINICIAN, RoleCode.ORG_ADMIN}),
        permissions_by_role_id={
            clinician_role: frozenset({Permission.CLINICAL_CONDITION_CREATE}),
            admin_role: frozenset({Permission.ORG_FACILITY_CREATE}),
        },
    )
    scoped_a = principal.for_organization(org_a)
    scoped_b = principal.for_organization(org_b)
    assert Permission.CLINICAL_CONDITION_CREATE in scoped_a.permission_codes
    assert Permission.ORG_FACILITY_CREATE not in scoped_a.permission_codes
    assert Permission.ORG_FACILITY_CREATE in scoped_b.permission_codes
    assert Permission.CLINICAL_CONDITION_CREATE not in scoped_b.permission_codes
    assert scoped_a.role_codes == frozenset({RoleCode.CLINICIAN})
    assert scoped_b.role_codes == frozenset({RoleCode.ORG_ADMIN})


def test_for_organization_scopes_facilities_and_empty_means_org_wide() -> None:
    org_a = uuid4()
    org_b = uuid4()
    a1 = uuid4()
    b1 = uuid4()
    role_a = uuid4()
    role_b = uuid4()
    principal = Principal(
        user=_user(),
        memberships=(
            _membership(
                organization_id=org_a,
                role_id=role_a,
                role_code=RoleCode.CLINICIAN,
                facility_id=a1,
            ),
            _membership(
                organization_id=org_b,
                role_id=role_b,
                role_code=RoleCode.ORG_ADMIN,
                facility_id=None,
            ),
        ),
        permission_codes=frozenset({Permission.CLINICAL_CONDITION_READ}),
        organization_ids=frozenset({org_a, org_b}),
        facility_ids=frozenset({a1}),
        role_codes=frozenset({RoleCode.CLINICIAN, RoleCode.ORG_ADMIN}),
        permissions_by_role_id={
            role_a: frozenset({Permission.CLINICAL_CONDITION_READ}),
            role_b: frozenset({Permission.ORG_FACILITY_CREATE}),
        },
    )
    scoped_a = principal.for_organization(org_a)
    scoped_b = principal.for_organization(org_b)
    assert scoped_a.facility_ids == frozenset({a1})
    assert scoped_b.facility_ids == frozenset()
    assert b1 not in scoped_a.facility_ids


def test_for_organization_keeps_platform_membership_and_tenant_role() -> None:
    org_a = uuid4()
    clinician_role = uuid4()
    platform_role = uuid4()
    principal = Principal(
        user=_user(),
        memberships=(
            _membership(
                organization_id=None, role_id=platform_role, role_code=RoleCode.PLATFORM_ADMIN
            ),
            _membership(
                organization_id=org_a, role_id=clinician_role, role_code=RoleCode.CLINICIAN
            ),
        ),
        permission_codes=frozenset(
            {
                Permission.IAM_PLATFORM,
                Permission.ORG_ORGANIZATION_CREATE,
                Permission.CLINICAL_CONDITION_CREATE,
            }
        ),
        organization_ids=frozenset({org_a}),
        facility_ids=frozenset(),
        role_codes=frozenset({RoleCode.PLATFORM_ADMIN, RoleCode.CLINICIAN}),
        permissions_by_role_id={
            platform_role: frozenset({Permission.IAM_PLATFORM, Permission.ORG_ORGANIZATION_CREATE}),
            clinician_role: frozenset({Permission.CLINICAL_CONDITION_CREATE}),
        },
    )
    scoped = principal.for_organization(org_a)
    assert Permission.IAM_PLATFORM in scoped.permission_codes
    assert Permission.ORG_ORGANIZATION_CREATE in scoped.permission_codes
    assert Permission.CLINICAL_CONDITION_CREATE in scoped.permission_codes
    assert scoped.organization_ids == frozenset({org_a})
    assert {item.organization_id for item in scoped.memberships} == {None, org_a}
    again = scoped.for_organization(org_a)
    assert again.permission_codes == scoped.permission_codes
    foreign = principal.for_organization(uuid4())
    assert Permission.IAM_PLATFORM in foreign.permission_codes
    assert Permission.ORG_ORGANIZATION_CREATE in foreign.permission_codes
    assert Permission.CLINICAL_CONDITION_CREATE not in foreign.permission_codes
    assert foreign.organization_ids == frozenset()


def _snapshot(principal: Principal) -> tuple[object, ...]:
    return (
        tuple(item.id for item in principal.memberships),
        tuple(item.organization_id for item in principal.memberships),
        principal.permission_codes,
        principal.organization_ids,
        principal.facility_ids,
        principal.role_codes,
        frozenset(principal.permissions_by_role_id.items()),
        principal.has_platform_scope,
    )


def test_for_organization_is_idempotent_and_immutable() -> None:
    org_a = uuid4()
    org_b = uuid4()
    clinician_role = uuid4()
    admin_role = uuid4()
    principal = Principal(
        user=_user(),
        memberships=(
            _membership(
                organization_id=org_a, role_id=clinician_role, role_code=RoleCode.CLINICIAN
            ),
            _membership(organization_id=org_b, role_id=admin_role, role_code=RoleCode.ORG_ADMIN),
        ),
        permission_codes=frozenset(
            {Permission.CLINICAL_CONDITION_CREATE, Permission.ORG_FACILITY_CREATE}
        ),
        organization_ids=frozenset({org_a, org_b}),
        facility_ids=frozenset(),
        role_codes=frozenset({RoleCode.CLINICIAN, RoleCode.ORG_ADMIN}),
        permissions_by_role_id={
            clinician_role: frozenset({Permission.CLINICAL_CONDITION_CREATE}),
            admin_role: frozenset({Permission.ORG_FACILITY_CREATE}),
        },
    )
    original = _snapshot(principal)
    scoped = principal.for_organization(org_a)
    again = scoped.for_organization(org_a)
    assert scoped is not principal
    assert again is not scoped
    assert _snapshot(principal) == original
    assert _snapshot(scoped) == _snapshot(again)
    assert len(scoped.memberships) == len(set(item.id for item in scoped.memberships))
    assert admin_role not in scoped.permissions_by_role_id
    hopped = scoped.for_organization(org_b)
    assert hopped.permission_codes == frozenset()
    assert hopped.organization_ids == frozenset()
    assert hopped.memberships == ()
    assert Permission.ORG_FACILITY_CREATE not in hopped.permission_codes


def test_for_organization_same_org_unions_roles_and_explicit_facilities() -> None:
    org_a = uuid4()
    a1 = uuid4()
    a2 = uuid4()
    clinician_role = uuid4()
    registrar_role = uuid4()
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
                organization_id=org_a,
                role_id=registrar_role,
                role_code=RoleCode.REGISTRAR,
                facility_id=a2,
            ),
        ),
        permission_codes=frozenset(
            {Permission.CLINICAL_CONDITION_CREATE, Permission.MPI_IDENTITY_CREATE}
        ),
        organization_ids=frozenset({org_a}),
        facility_ids=frozenset({a1, a2}),
        role_codes=frozenset({RoleCode.CLINICIAN, RoleCode.REGISTRAR}),
        permissions_by_role_id={
            clinician_role: frozenset({Permission.CLINICAL_CONDITION_CREATE}),
            registrar_role: frozenset({Permission.MPI_IDENTITY_CREATE}),
        },
    )
    scoped = principal.for_organization(org_a)
    assert Permission.CLINICAL_CONDITION_CREATE in scoped.permission_codes
    assert Permission.MPI_IDENTITY_CREATE in scoped.permission_codes
    assert scoped.facility_ids == frozenset({a1, a2})
    assert scoped.facility_ids != frozenset()


def test_for_organization_same_org_org_wide_membership_wins_facility_empty_list() -> None:
    org_a = uuid4()
    a1 = uuid4()
    clinician_role = uuid4()
    registrar_role = uuid4()
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
                organization_id=org_a,
                role_id=registrar_role,
                role_code=RoleCode.REGISTRAR,
                facility_id=None,
            ),
        ),
        permission_codes=frozenset({Permission.CLINICAL_CONDITION_CREATE}),
        organization_ids=frozenset({org_a}),
        facility_ids=frozenset({a1}),
        role_codes=frozenset({RoleCode.CLINICIAN, RoleCode.REGISTRAR}),
        permissions_by_role_id={
            clinician_role: frozenset({Permission.CLINICAL_CONDITION_CREATE}),
            registrar_role: frozenset({Permission.MPI_IDENTITY_CREATE}),
        },
    )
    scoped = principal.for_organization(org_a)
    assert scoped.facility_ids == frozenset()


def test_for_organization_platform_hybrid_does_not_copy_b_tenant() -> None:
    org_a = uuid4()
    org_b = uuid4()
    platform_role = uuid4()
    admin_role = uuid4()
    clinician_role = uuid4()
    principal = Principal(
        user=_user(),
        memberships=(
            _membership(
                organization_id=None, role_id=platform_role, role_code=RoleCode.PLATFORM_ADMIN
            ),
            _membership(organization_id=org_a, role_id=admin_role, role_code=RoleCode.ORG_ADMIN),
            _membership(
                organization_id=org_b, role_id=clinician_role, role_code=RoleCode.CLINICIAN
            ),
        ),
        permission_codes=frozenset(
            {
                Permission.IAM_PLATFORM,
                Permission.ORG_FACILITY_CREATE,
                Permission.CLINICAL_CONDITION_CREATE,
            }
        ),
        organization_ids=frozenset({org_a, org_b}),
        facility_ids=frozenset(),
        role_codes=frozenset({RoleCode.PLATFORM_ADMIN, RoleCode.ORG_ADMIN, RoleCode.CLINICIAN}),
        permissions_by_role_id={
            platform_role: frozenset({Permission.IAM_PLATFORM, Permission.ORG_ORGANIZATION_CREATE}),
            admin_role: frozenset({Permission.ORG_FACILITY_CREATE}),
            clinician_role: frozenset({Permission.CLINICAL_CONDITION_CREATE}),
        },
    )
    scoped_a = principal.for_organization(org_a)
    tenant_orgs = {item.organization_id for item in scoped_a.memberships}
    assert tenant_orgs == {None, org_a}
    assert org_b not in tenant_orgs
    assert Permission.IAM_PLATFORM in scoped_a.permission_codes
    assert Permission.ORG_FACILITY_CREATE in scoped_a.permission_codes
    assert Permission.CLINICAL_CONDITION_CREATE not in scoped_a.permission_codes
    assert clinician_role not in scoped_a.permissions_by_role_id
    scoped_b = principal.for_organization(org_b)
    assert Permission.CLINICAL_CONDITION_CREATE in scoped_b.permission_codes
    assert Permission.ORG_FACILITY_CREATE not in scoped_b.permission_codes
    missing = principal.for_organization(uuid4())
    assert missing.organization_ids == frozenset()
    assert Permission.IAM_PLATFORM in missing.permission_codes
    assert Permission.ORG_FACILITY_CREATE not in missing.permission_codes
    assert Permission.CLINICAL_CONDITION_CREATE not in missing.permission_codes
