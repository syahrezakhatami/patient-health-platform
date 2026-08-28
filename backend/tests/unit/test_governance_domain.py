
from app.modules.governance.domain.enums import (
    FeatureActivationState,
    ProviderCapabilityState,
)
from app.modules.governance.domain.models import ProviderCapability
from app.modules.governance.domain.resolver import resolve_provider_layer
from app.modules.governance.domain.transitions import (
    validate_activation_transition,
    validate_provider_transition,
)
from app.shared.types.ids import new_id


def test_provider_same_state_noop() -> None:
    assert (
        validate_provider_transition(
            ProviderCapabilityState.AVAILABLE,
            ProviderCapabilityState.AVAILABLE,
        )
        is False
    )


def test_activation_same_state_noop() -> None:
    assert (
        validate_activation_transition(
            FeatureActivationState.ACTIVE,
            FeatureActivationState.ACTIVE,
        )
        is False
    )


def test_resolve_unregistered_capability() -> None:
    result = resolve_provider_layer(None)
    assert result.registered is False
    assert result.available is False


def test_resolve_suspended_capability() -> None:
    capability = ProviderCapability(
        id=new_id(),
        feature_id="test",
        feature_version="1.0.0",
        frozen_release_tag=None,
        provider_state=ProviderCapabilityState.SUSPENDED,
        governance_required=False,
        row_version=1,
    )
    result = resolve_provider_layer(capability)
    assert result.denial_reason is not None
    assert result.denial_reason.value == "DENIED_PROVIDER"
