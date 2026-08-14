import pytest
from app.core.config import Settings
from app.modules.authorization.application.deny_by_default import DenyByDefaultPDP
from app.modules.authorization.domain.models import AuthorizationContext
from app.shared.enums import (
    AuthorshipKind,
    InformationSource,
    PrincipalType,
    VerificationStatus,
)
from app.shared.types.ids import new_id
from app.shared.types.provenance import ProvenanceRef
from pydantic import SecretStr, ValidationError

pytestmark = pytest.mark.unit


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "php-test")
    monkeypatch.setenv("APP_ENV", "test")
    settings = Settings()
    assert settings.app_name == "php-test"
    assert settings.app_env == "test"


def test_production_rejects_invalid_env() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="not-a-real-env")  # type: ignore[arg-type]


def test_dev_hs256_not_allowed_in_production() -> None:
    settings = Settings(
        app_env="production",
        auth_dev_hs256_secret=SecretStr("x"),
    )
    assert settings.allow_dev_hs256 is False


def test_pdp_denies_by_default() -> None:
    pdp = DenyByDefaultPDP()
    decision = pdp.evaluate(
        AuthorizationContext(
            actor_id=new_id(),
            principal_type=PrincipalType.PRACTITIONER,
            organization_id=new_id(),
            facility_id=new_id(),
            roles=("doctor",),
            scopes=("treatment",),
            patient_id=new_id(),
            purpose="treatment",
            emergency_access_id=None,
            resource_type="Patient",
            action="read",
        )
    )
    assert decision.allowed is False
    assert decision.policy_reference == "pdp.wave0.deny_by_default"
    assert "audit_denial" in decision.obligations


def test_new_id_is_uuid_not_nik() -> None:
    first = new_id()
    second = new_id()
    assert first != second
    assert str(first) != "NIK"


def test_provenance_ref_is_not_clinical_truth() -> None:
    ref = ProvenanceRef(
        authorship_kind=AuthorshipKind.IMPORTED,
        information_source=InformationSource.EXTERNAL_SYSTEM,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    assert ref.clinical_effective_at is None
    assert ref.authorship_kind is AuthorshipKind.IMPORTED
