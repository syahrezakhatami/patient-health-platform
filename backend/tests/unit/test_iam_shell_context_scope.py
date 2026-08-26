from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.core.errors import NotFoundError
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.iam.application.shell_context import (
    ShellContextService,
    explicit_facility_ids,
    facility_scope_kind,
    tenant_permission_codes,
    tenant_role_codes,
    work_facility_required,
)
from app.modules.iam.application.shell_schemas import FacilityScopeKind
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


def test_tenant_permissions_exclude_platform_catalog() -> None:
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
        permission_codes=frozenset({Permission.IAM_PLATFORM, Permission.CLINICAL_CONDITION_CREATE}),
        organization_ids=frozenset({org_a}),
        facility_ids=frozenset(),
        role_codes=frozenset({RoleCode.PLATFORM_ADMIN, RoleCode.CLINICIAN}),
        permissions_by_role_id={
            platform_role: frozenset({Permission.IAM_PLATFORM, Permission.ORG_ORGANIZATION_CREATE}),
            clinician_role: frozenset({Permission.CLINICAL_CONDITION_CREATE}),
        },
    ).for_organization(org_a)
    assert Permission.IAM_PLATFORM in principal.permission_codes
    assert tenant_permission_codes(principal) == [Permission.CLINICAL_CONDITION_CREATE]
    assert tenant_role_codes(principal) == [RoleCode.CLINICIAN]
    assert Permission.IAM_PLATFORM not in tenant_permission_codes(principal)
    assert tenant_permission_codes(principal) == sorted(tenant_permission_codes(principal))


def test_facility_scope_all_in_organization_for_null_binding() -> None:
    org_a = uuid4()
    role_id = uuid4()
    principal = Principal(
        user=_user(),
        memberships=(
            _membership(
                organization_id=org_a,
                role_id=role_id,
                role_code=RoleCode.CLINICIAN,
                facility_id=None,
            ),
        ),
        permission_codes=frozenset(),
        organization_ids=frozenset({org_a}),
        facility_ids=frozenset(),
        role_codes=frozenset({RoleCode.CLINICIAN}),
        permissions_by_role_id={role_id: frozenset()},
    ).for_organization(org_a)
    assert facility_scope_kind(principal) is FacilityScopeKind.ALL_IN_ORGANIZATION
    assert explicit_facility_ids(principal) == frozenset()


def test_facility_scope_explicit_union_and_org_wide_wins() -> None:
    org_a = uuid4()
    a1 = uuid4()
    a2 = uuid4()
    clinician_role = uuid4()
    registrar_role = uuid4()
    explicit = Principal(
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
        permission_codes=frozenset(),
        organization_ids=frozenset({org_a}),
        facility_ids=frozenset({a1, a2}),
        role_codes=frozenset({RoleCode.CLINICIAN, RoleCode.REGISTRAR}),
        permissions_by_role_id={clinician_role: frozenset(), registrar_role: frozenset()},
    ).for_organization(org_a)
    assert facility_scope_kind(explicit) is FacilityScopeKind.EXPLICIT
    assert explicit_facility_ids(explicit) == frozenset({a1, a2})

    mixed = Principal(
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
        permission_codes=frozenset(),
        organization_ids=frozenset({org_a}),
        facility_ids=frozenset(),
        role_codes=frozenset({RoleCode.CLINICIAN, RoleCode.REGISTRAR}),
        permissions_by_role_id={clinician_role: frozenset(), registrar_role: frozenset()},
    ).for_organization(org_a)
    assert facility_scope_kind(mixed) is FacilityScopeKind.ALL_IN_ORGANIZATION


_SHELL_PATHS = {
    "/api/v1/iam/me/organizations",
    "/api/v1/iam/me/context",
    "/api/v1/organizations/{organization_id}/facilities/accessible",
}


def test_shell_route_surface_is_exactly_three_gets(app) -> None:
    paths = app.openapi()["paths"]
    for path in _SHELL_PATHS:
        assert set(paths[path].keys()) == {"get"}
    assert "/fhir" not in str(paths)
    assert all(not item.startswith("/api/v2") for item in paths)


def test_work_facility_required_is_false_for_org_wide_and_true_for_explicit() -> None:
    org_a = uuid4()
    a1 = uuid4()
    role_id = uuid4()
    org_wide = Principal(
        user=_user(),
        memberships=(
            _membership(
                organization_id=org_a,
                role_id=role_id,
                role_code=RoleCode.CLINICIAN,
                facility_id=None,
            ),
        ),
        permission_codes=frozenset(),
        organization_ids=frozenset({org_a}),
        facility_ids=frozenset(),
        role_codes=frozenset({RoleCode.CLINICIAN}),
        permissions_by_role_id={role_id: frozenset()},
    ).for_organization(org_a)
    assert work_facility_required(org_wide) is False
    explicit = Principal(
        user=_user(),
        memberships=(
            _membership(
                organization_id=org_a, role_id=role_id, role_code=RoleCode.CLINICIAN, facility_id=a1
            ),
        ),
        permission_codes=frozenset(),
        organization_ids=frozenset({org_a}),
        facility_ids=frozenset({a1}),
        role_codes=frozenset({RoleCode.CLINICIAN}),
        permissions_by_role_id={role_id: frozenset()},
    ).for_organization(org_a)
    assert work_facility_required(explicit) is True


async def test_header_path_mismatch_and_no_membership_skip_facility_query(monkeypatch) -> None:
    calls = {"facilities": 0, "orgs": 0}

    class _Repo:
        def __init__(self, session: object) -> None:
            del session

        async def list_facilities_for_shell(self, *args: object, **kwargs: object) -> list[object]:
            del args, kwargs
            calls["facilities"] += 1
            return []

        async def get_organization(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            calls["orgs"] += 1
            return None

        async def list_organizations_by_ids(self, *args: object, **kwargs: object) -> list[object]:
            del args, kwargs
            return []

    monkeypatch.setattr("app.modules.iam.application.shell_context.OrganizationRepository", _Repo)
    service = ShellContextService(session=None, pdp=None, audit=None)  # type: ignore[arg-type]
    org_a = uuid4()
    org_b = uuid4()
    role_id = uuid4()
    principal = Principal(
        user=_user(),
        memberships=(
            _membership(organization_id=org_a, role_id=role_id, role_code=RoleCode.CLINICIAN),
        ),
        permission_codes=frozenset({Permission.ORG_FACILITY_READ}),
        organization_ids=frozenset({org_a}),
        facility_ids=frozenset(),
        role_codes=frozenset({RoleCode.CLINICIAN}),
        permissions_by_role_id={role_id: frozenset({Permission.ORG_FACILITY_READ})},
    )
    with pytest.raises(NotFoundError):
        await service.list_accessible_facilities(
            principal,
            organization_id=org_b,
            header_organization_id=org_a,
            correlation_id=None,
        )
    with pytest.raises(NotFoundError):
        await service.list_accessible_facilities(
            principal,
            organization_id=org_a,
            header_organization_id=org_b,
            correlation_id=None,
        )
    with pytest.raises(NotFoundError):
        await service.list_accessible_facilities(
            principal,
            organization_id=org_b,
            header_organization_id=org_b,
            correlation_id=None,
        )
    assert calls["facilities"] == 0
    assert calls["orgs"] == 0
