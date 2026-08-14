from decimal import Decimal
from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.core.logging import _redact_secrets
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.clinical.domain.enums import ObservationStatus, ObservationValueType
from app.modules.clinical.domain.lifecycle import (
    OBSERVATION_TRANSITIONS,
    assert_observation_can_amend,
    assert_observation_mutable,
)
from app.modules.clinical.domain.observation_values import parse_observation_value
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


def test_observation_value_types_reject_conflicting_fields() -> None:
    numeric = parse_observation_value(
        value_type=ObservationValueType.NUMERIC,
        value_numeric=Decimal("72"),
        value_text=None,
        value_boolean=None,
        value_coded=None,
        unit="beats/min",
        range_low=Decimal("60"),
        range_high=Decimal("100"),
    )
    assert numeric.numeric == Decimal("72")
    with pytest.raises(AppError, match="value_numeric only"):
        parse_observation_value(
            value_type=ObservationValueType.NUMERIC,
            value_numeric=Decimal("72"),
            value_text="72",
            value_boolean=None,
            value_coded=None,
            unit="beats/min",
            range_low=None,
            range_high=None,
        )
    with pytest.raises(AppError, match="requires a unit"):
        parse_observation_value(
            value_type=ObservationValueType.NUMERIC,
            value_numeric=Decimal("72"),
            value_text=None,
            value_boolean=None,
            value_coded=None,
            unit=None,
            range_low=None,
            range_high=None,
        )
    with pytest.raises(AppError, match="value_text only"):
        parse_observation_value(
            value_type=ObservationValueType.TEXT,
            value_numeric=Decimal("1"),
            value_text="alert",
            value_boolean=None,
            value_coded=None,
            unit=None,
            range_low=None,
            range_high=None,
        )
    with pytest.raises(AppError, match="value_boolean only"):
        parse_observation_value(
            value_type=ObservationValueType.BOOLEAN,
            value_numeric=None,
            value_text="true",
            value_boolean=True,
            value_coded=None,
            unit=None,
            range_low=None,
            range_high=None,
        )
    coded = parse_observation_value(
        value_type=ObservationValueType.CODED,
        value_numeric=None,
        value_text=None,
        value_boolean=None,
        value_coded={"system": "http://example.org", "code": "POS"},
        unit=None,
        range_low=None,
        range_high=None,
    )
    assert coded.coded is not None
    assert coded.coded.code == "POS"


def test_observation_lifecycle_and_immutability() -> None:
    assert ObservationStatus.AMENDED in OBSERVATION_TRANSITIONS[ObservationStatus.FINAL]
    assert ObservationStatus.ENTERED_IN_ERROR in OBSERVATION_TRANSITIONS[ObservationStatus.FINAL]
    assert_observation_can_amend(ObservationStatus.FINAL)
    assert_observation_can_amend(ObservationStatus.AMENDED)
    with pytest.raises(AppError, match="immutable"):
        assert_observation_mutable(ObservationStatus.ENTERED_IN_ERROR)
    with pytest.raises(AppError, match="immutable"):
        assert_observation_can_amend(ObservationStatus.ENTERED_IN_ERROR)


def test_pdp_allows_observation_permission_and_denies_unknown_lab_alias() -> None:
    pdp = Wave1PolicyPDP()
    org_id = uuid4()
    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=(Permission.CLINICAL_OBSERVATION_CREATE,),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Observation",
            action=Permission.CLINICAL_OBSERVATION_CREATE,
            actor_organization_ids=(org_id,),
        )
    )
    assert allowed.allowed is True
    unknown = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=("clinical.laboratory.create",),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Laboratory",
            action="clinical.laboratory.create",
            actor_organization_ids=(org_id,),
        )
    )
    assert unknown.allowed is False
    assert unknown.reason == "deny_by_default"


def test_observation_values_are_redacted_from_log_events() -> None:
    redacted = _redact_secrets(
        None,  # type: ignore[arg-type]
        "info",
        {
            "value_text": "patient appears pale",
            "value_numeric": "36.6",
            "value_boolean": True,
            "value_code": "LA6113-5",
            "value_code_system": "http://loinc.org",
            "value_code_display": "Positive",
            "value_coded": {"system": "http://loinc.org", "code": "LA6113-5"},
            "event": "request",
        },
    )
    assert redacted["value_text"] == "[REDACTED]"
    assert redacted["value_numeric"] == "[REDACTED]"
    assert redacted["value_boolean"] == "[REDACTED]"
    assert redacted["value_code"] == "[REDACTED]"
    assert redacted["value_code_system"] == "[REDACTED]"
    assert redacted["value_code_display"] == "[REDACTED]"
    assert redacted["value_coded"] == "[REDACTED]"
    assert redacted["event"] == "request"
