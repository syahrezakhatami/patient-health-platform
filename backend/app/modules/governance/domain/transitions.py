from app.core.errors import AppError
from app.modules.governance.domain.enums import (
    FeatureActivationState,
    ProviderCapabilityState,
)

_PROVIDER_TRANSITIONS: dict[tuple[ProviderCapabilityState, ProviderCapabilityState], bool] = {
    (ProviderCapabilityState.AVAILABLE, ProviderCapabilityState.SUSPENDED): True,
    (ProviderCapabilityState.SUSPENDED, ProviderCapabilityState.AVAILABLE): True,
    (ProviderCapabilityState.AVAILABLE, ProviderCapabilityState.RETIRED): True,
    (ProviderCapabilityState.SUSPENDED, ProviderCapabilityState.RETIRED): True,
}


def validate_provider_transition(
    current: ProviderCapabilityState,
    target: ProviderCapabilityState,
) -> bool:
    if current == target:
        return False
    if current == ProviderCapabilityState.RETIRED:
        raise AppError("invalid_transition", "Provider capability is retired", status_code=409)
    return _PROVIDER_TRANSITIONS.get((current, target), False)


_ACTIVATION_TRANSITIONS: dict[
    tuple[FeatureActivationState | None, FeatureActivationState],
    bool,
] = {
    (None, FeatureActivationState.PENDING_APPROVAL): True,
    (FeatureActivationState.PENDING_APPROVAL, FeatureActivationState.APPROVED): True,
    (FeatureActivationState.PENDING_APPROVAL, FeatureActivationState.RETIRED): True,
    (FeatureActivationState.APPROVED, FeatureActivationState.ACTIVE): True,
    (FeatureActivationState.APPROVED, FeatureActivationState.PENDING_APPROVAL): True,
    (FeatureActivationState.APPROVED, FeatureActivationState.RETIRED): True,
    (FeatureActivationState.ACTIVE, FeatureActivationState.SUSPENDED): True,
    (FeatureActivationState.SUSPENDED, FeatureActivationState.ACTIVE): True,
    (FeatureActivationState.ACTIVE, FeatureActivationState.RETIRED): True,
    (FeatureActivationState.SUSPENDED, FeatureActivationState.RETIRED): True,
}


def validate_activation_transition(
    current: FeatureActivationState | None,
    target: FeatureActivationState,
) -> bool:
    if current == target:
        return False
    if current == FeatureActivationState.RETIRED:
        raise AppError("invalid_transition", "Feature activation is retired", status_code=409)
    allowed = _ACTIVATION_TRANSITIONS.get((current, target), False)
    if not allowed:
        raise AppError(
            "invalid_transition",
            "Feature activation transition is not allowed",
            status_code=409,
        )
    return True
