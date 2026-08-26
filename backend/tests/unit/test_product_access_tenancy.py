from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.api.v1.deps import require_patient_audience, require_staff_audience
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.facility_scope import facility_tenant_decision
from app.modules.authorization.application.product_access_pdp import ProductAccessPDP
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import (
    PATIENT_PERMISSIONS,
    PLATFORM_ADMIN_PERMISSIONS,
    Permission,
    RoleCode,
)
from app.modules.authorization.domain.models import AuthorizationContext, AuthorizationDecision
from app.modules.iam.infrastructure.jwt_oidc_validator import JwtOidcTokenValidator
from app.modules.patient_access.application.patient_pdp import PatientSelfAccessPDP
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


def _staff_context(**overrides: object) -> AuthorizationContext:
    org = uuid4()
    values: dict[str, object] = {
        "actor_id": uuid4(),
        "principal_type": PrincipalType.STAFF,
        "organization_id": org,
        "facility_id": None,
        "roles": (RoleCode.CLINICIAN,),
        "scopes": (Permission.CLINICAL_CONDITION_READ,),
        "patient_id": None,
        "purpose": "TREATMENT",
        "emergency_access_id": None,
        "resource_type": "Condition",
        "action": Permission.CLINICAL_CONDITION_READ,
        "actor_organization_ids": (org,),
        "actor_facility_ids": (),
    }
    values.update(overrides)
    return AuthorizationContext(**values)  # type: ignore[arg-type]


def _patient_context(**overrides: object) -> AuthorizationContext:
    identity = uuid4()
    org = uuid4()
    values: dict[str, object] = {
        "actor_id": uuid4(),
        "principal_type": PrincipalType.PATIENT,
        "organization_id": org,
        "facility_id": None,
        "roles": (),
        "scopes": tuple(PATIENT_PERMISSIONS),
        "patient_id": identity,
        "purpose": "PATIENT_ACCESS",
        "emergency_access_id": None,
        "resource_type": "PatientAccount",
        "action": Permission.PATIENT_ACCOUNT_READ,
        "actor_organization_ids": (),
        "actor_facility_ids": (),
        "canonical_patient_identity_id": identity,
        "cluster_identity_ids": (identity,),
    }
    values.update(overrides)
    return AuthorizationContext(**values)  # type: ignore[arg-type]


def test_platform_admin_catalog_excludes_clinical_and_mpi() -> None:
    assert Permission.IAM_PLATFORM in PLATFORM_ADMIN_PERMISSIONS
    assert Permission.CLINICAL_CONDITION_READ not in PLATFORM_ADMIN_PERMISSIONS
    assert Permission.MPI_IDENTITY_READ not in PLATFORM_ADMIN_PERMISSIONS
    assert Permission.PATIENT_ACCOUNT_READ not in PLATFORM_ADMIN_PERMISSIONS


def test_dispatcher_denies_platform_clinical_even_with_stale_scope() -> None:
    pdp = ProductAccessPDP()
    org = uuid4()
    decision = pdp.evaluate(
        _staff_context(
            roles=(RoleCode.PLATFORM_ADMIN,),
            scopes=(Permission.IAM_PLATFORM, Permission.CLINICAL_CONDITION_READ),
            actor_organization_ids=(),
            organization_id=org,
        )
    )
    assert decision.allowed is False
    assert decision.reason == "platform_clinical_forbidden"


def test_dispatcher_denies_platform_mpi() -> None:
    pdp = ProductAccessPDP()
    decision = pdp.evaluate(
        _staff_context(
            roles=(RoleCode.PLATFORM_ADMIN,),
            scopes=(Permission.IAM_PLATFORM, Permission.MPI_IDENTITY_READ),
            action=Permission.MPI_IDENTITY_READ,
            resource_type="PatientIdentity",
            actor_organization_ids=(),
        )
    )
    assert decision.allowed is False
    assert decision.reason == "platform_clinical_forbidden"


def test_dispatcher_allows_clinician_clinical() -> None:
    pdp = ProductAccessPDP()
    decision = pdp.evaluate(_staff_context())
    assert decision.allowed is True


def test_dispatcher_routes_patient_to_self_access_pdp() -> None:
    pdp = ProductAccessPDP()
    decision = pdp.evaluate(_patient_context())
    assert decision.allowed is True
    assert decision.policy_reference == "pdp.patient.self"


def test_patient_pdp_conceals_other_patient() -> None:
    pdp = PatientSelfAccessPDP()
    other = uuid4()
    decision = pdp.evaluate(_patient_context(patient_id=other))
    assert decision.allowed is False
    assert decision.reason == "patient_identity_mismatch"


def test_patient_pdp_purpose_does_not_grant_wrong_identity() -> None:
    pdp = PatientSelfAccessPDP()
    decision = pdp.evaluate(_patient_context(patient_id=uuid4(), purpose="PATIENT_ACCESS"))
    assert decision.allowed is False


def test_patient_pdp_rejects_wrong_purpose() -> None:
    pdp = PatientSelfAccessPDP()
    decision = pdp.evaluate(_patient_context(purpose="TREATMENT"))
    assert decision.allowed is False
    assert decision.reason == "invalid_purpose"


def test_patient_record_read_requires_organization() -> None:
    pdp = PatientSelfAccessPDP()
    decision = pdp.evaluate(
        _patient_context(
            action=Permission.PATIENT_RECORD_READ,
            resource_type="PatientRecord",
            organization_id=None,
        )
    )
    assert decision.allowed is False
    assert decision.reason == "missing_organization_scope"


def test_patient_record_read_allows_cluster_member() -> None:
    pdp = PatientSelfAccessPDP()
    canonical = uuid4()
    historical = uuid4()
    org = uuid4()
    decision = pdp.evaluate(
        _patient_context(
            action=Permission.PATIENT_RECORD_READ,
            resource_type="PatientRecord",
            patient_id=historical,
            canonical_patient_identity_id=canonical,
            cluster_identity_ids=(canonical, historical),
            organization_id=org,
        )
    )
    assert decision.allowed is True


def test_patient_principal_cannot_exercise_clinical_or_mpi_actions() -> None:
    pdp = ProductAccessPDP()
    decision = pdp.evaluate(
        _patient_context(
            action=Permission.CLINICAL_CONDITION_READ,
            resource_type="Condition",
        )
    )
    assert decision.allowed is False
    mpi = pdp.evaluate(
        _patient_context(
            action=Permission.MPI_IDENTITY_READ,
            resource_type="PatientIdentity",
        )
    )
    assert mpi.allowed is False
    iam = pdp.evaluate(
        _patient_context(
            action=Permission.IAM_PLATFORM,
            resource_type="Platform",
        )
    )
    assert iam.allowed is False


def test_dispatcher_denies_unknown_principal_type() -> None:
    pdp = ProductAccessPDP()
    decision = pdp.evaluate(_staff_context(principal_type=PrincipalType.SYSTEM))
    assert decision.allowed is False
    assert decision.reason == "principal_type_denied"


def test_dispatcher_does_not_fall_through_ai_service_to_staff() -> None:
    pdp = ProductAccessPDP()
    decision = pdp.evaluate(
        _staff_context(
            principal_type=PrincipalType.AI_SERVICE,
            scopes=(Permission.CLINICAL_CONDITION_READ,),
        )
    )
    assert decision.allowed is False
    assert decision.policy_reference == "pdp.product.unknown_principal"


def test_staff_roles_do_not_receive_patient_permissions() -> None:
    from app.modules.authorization.domain.catalog import ROLE_PERMISSIONS

    for perms in ROLE_PERMISSIONS.values():
        assert PATIENT_PERMISSIONS.isdisjoint(perms)


def test_wave1_pdp_source_has_no_product_access_dispatch() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "authorization"
        / "application"
        / "wave1_pdp.py"
    ).read_text(encoding="utf-8")
    assert "ProductAccessPDP" not in source
    assert "PatientSelfAccessPDP" not in source
    assert "PrincipalType.PATIENT" not in source


def test_frozen_wave1_pdp_empty_facility_list_still_allows_any_facility_uuid() -> None:
    """Wave1 cannot see facility.organization_id. Tenant check lives in authorize()."""
    pdp = Wave1PolicyPDP()
    org = uuid4()
    decision = pdp.evaluate(
        _staff_context(
            organization_id=org,
            facility_id=uuid4(),
            actor_organization_ids=(org,),
            actor_facility_ids=(),
        )
    )
    assert decision.allowed is True


@pytest.mark.asyncio
async def test_null_facility_skips_tenant_lookup() -> None:
    decision = await facility_tenant_decision(
        MagicMock(),
        facility_id=None,
        organization_id=uuid4(),
    )
    assert decision is None


@pytest.mark.asyncio
async def test_facility_without_organization_is_denied() -> None:
    decision = await facility_tenant_decision(
        MagicMock(),
        facility_id=uuid4(),
        organization_id=None,
    )
    assert decision is not None
    assert decision.allowed is False
    assert decision.reason == "facility_organization_mismatch"


@pytest.mark.asyncio
async def test_unknown_facility_is_concealed() -> None:
    with patch(
        "app.modules.authorization.application.facility_scope.OrganizationRepository"
    ) as repo_cls:
        repo_cls.return_value.get_facility = AsyncMock(return_value=None)
        decision = await facility_tenant_decision(
            MagicMock(),
            facility_id=uuid4(),
            organization_id=uuid4(),
        )
    assert decision is not None
    assert decision.allowed is False
    assert decision.reason == "facility_not_found"


@pytest.mark.asyncio
async def test_foreign_facility_is_tenant_mismatch() -> None:
    org = uuid4()
    with patch(
        "app.modules.authorization.application.facility_scope.OrganizationRepository"
    ) as repo_cls:
        repo_cls.return_value.get_facility = AsyncMock(
            return_value=SimpleNamespace(organization_id=uuid4())
        )
        decision = await facility_tenant_decision(
            MagicMock(),
            facility_id=uuid4(),
            organization_id=org,
        )
    assert decision is not None
    assert decision.allowed is False
    assert decision.reason == "facility_organization_mismatch"


@pytest.mark.asyncio
async def test_same_org_facility_passes_tenant_lookup() -> None:
    org = uuid4()
    with patch(
        "app.modules.authorization.application.facility_scope.OrganizationRepository"
    ) as repo_cls:
        repo_cls.return_value.get_facility = AsyncMock(
            return_value=SimpleNamespace(organization_id=org)
        )
        decision = await facility_tenant_decision(
            MagicMock(),
            facility_id=uuid4(),
            organization_id=org,
        )
    assert decision is None


class _DenyPDP:
    def evaluate(self, context: object) -> AuthorizationDecision:
        return AuthorizationDecision(
            allowed=False,
            reason="platform_clinical_forbidden",
            policy_reference="pdp.product.platform_phi",
            obligations=("audit_denial",),
        )


class _AllowPDP:
    def evaluate(self, context: object) -> AuthorizationDecision:
        return AuthorizationDecision(
            allowed=True,
            reason="permission_granted",
            policy_reference="pdp.wave1.permission_granted",
            obligations=("audit_success",),
        )


@pytest.mark.asyncio
async def test_authorize_skips_facility_lookup_when_pdp_denies() -> None:
    audit = AsyncMock()
    with patch(
        "app.modules.authorization.application.authorize.facility_tenant_decision",
        new_callable=AsyncMock,
    ) as tenant:
        with pytest.raises(ForbiddenError, match="Not authorized"):
            await authorize(
                _DenyPDP(),
                audit,
                session=MagicMock(),
                principal=None,
                action="clinical.condition.create",
                resource_type="Condition",
                organization_id=uuid4(),
                facility_id=uuid4(),
            )
        tenant.assert_not_called()


@pytest.mark.asyncio
async def test_authorize_conceals_foreign_facility_after_pdp_allow() -> None:
    audit = AsyncMock()
    with patch(
        "app.modules.authorization.application.authorize.facility_tenant_decision",
        new_callable=AsyncMock,
        return_value=AuthorizationDecision(
            allowed=False,
            reason="facility_organization_mismatch",
            policy_reference="pdp.product.facility_tenant",
            obligations=("audit_denial",),
        ),
    ):
        with pytest.raises(NotFoundError, match="Resource not found"):
            await authorize(
                _AllowPDP(),
                audit,
                session=MagicMock(),
                principal=None,
                action="clinical.condition.create",
                resource_type="Condition",
                organization_id=uuid4(),
                facility_id=uuid4(),
            )


def test_frozen_wave1_pdp_file_still_allows_platform_scope_directly() -> None:
    pdp = Wave1PolicyPDP()
    decision = pdp.evaluate(
        _staff_context(
            scopes=(Permission.IAM_PLATFORM, Permission.CLINICAL_CONDITION_READ),
            actor_organization_ids=(),
        )
    )
    assert decision.allowed is True
    assert decision.reason == "platform_scope"


def _request_with_audiences() -> SimpleNamespace:
    settings = SimpleNamespace(
        auth_audience="php-api",
        auth_platform_audience="php-platform",
        auth_patient_audience="php-patient",
    )
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))


def test_staff_audience_rejects_patient_token() -> None:
    with pytest.raises(UnauthorizedError):
        require_staff_audience(SimpleNamespace(audience="php-patient"), _request_with_audiences())


def test_patient_audience_rejects_staff_token() -> None:
    with pytest.raises(UnauthorizedError):
        require_patient_audience(SimpleNamespace(audience="php-api"), _request_with_audiences())


@pytest.mark.asyncio
async def test_mixed_audience_array_is_rejected() -> None:
    from tests.conftest import make_settings, mint_token

    validator = JwtOidcTokenValidator(make_settings())
    token = mint_token(extra={"aud": ["php-api", "php-patient"]})
    with pytest.raises(UnauthorizedError, match="audience"):
        await validator.validate(token)


@pytest.mark.asyncio
async def test_single_list_audience_is_accepted() -> None:
    from tests.conftest import make_settings, mint_token

    validator = JwtOidcTokenValidator(make_settings())
    token = mint_token(extra={"aud": ["php-api"]})
    context = await validator.validate(token)
    assert context.audience == "php-api"


@pytest.mark.asyncio
async def test_malformed_and_missing_audience_are_rejected() -> None:
    from datetime import UTC, datetime, timedelta

    import jwt
    from tests.conftest import TEST_SECRET, make_settings, mint_token

    validator = JwtOidcTokenValidator(make_settings())
    with pytest.raises(UnauthorizedError, match="audience"):
        await validator.validate(mint_token(aud="other-api"))
    with pytest.raises(UnauthorizedError):
        await validator.validate(mint_token(extra={"aud": []}))
    with pytest.raises(UnauthorizedError):
        await validator.validate(mint_token(extra={"aud": 123}))
    missing = jwt.encode(
        {
            "sub": "user-1",
            "iss": "http://localhost:8080/realms/php-dev",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "iat": datetime.now(UTC),
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError):
        await validator.validate(missing)
