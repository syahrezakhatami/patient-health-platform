from decimal import Decimal
from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.core.logging import _redact_secrets
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.clinical.application.services import _parse_medication_dose
from app.modules.clinical.domain.enums import MedicationStatus
from app.modules.clinical.domain.lifecycle import (
    MEDICATION_TRANSITIONS,
    assert_medication_can_stop,
    assert_medication_mutable,
)
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


def test_medication_dose_requires_both_or_neither() -> None:
    assert _parse_medication_dose(None, None) == (None, None)
    assert _parse_medication_dose(Decimal("500"), "mg") == (Decimal("500"), "mg")
    with pytest.raises(AppError, match="dose_numeric and dose_unit"):
        _parse_medication_dose(Decimal("500"), None)
    with pytest.raises(AppError, match="dose_numeric and dose_unit"):
        _parse_medication_dose(None, "mg")


def test_medication_lifecycle_and_immutability() -> None:
    assert MedicationStatus.STOPPED in MEDICATION_TRANSITIONS[MedicationStatus.ACTIVE]
    assert MedicationStatus.ENTERED_IN_ERROR in MEDICATION_TRANSITIONS[MedicationStatus.ACTIVE]
    assert MedicationStatus.ENTERED_IN_ERROR in MEDICATION_TRANSITIONS[MedicationStatus.STOPPED]
    assert MEDICATION_TRANSITIONS[MedicationStatus.ENTERED_IN_ERROR] == frozenset()
    assert_medication_can_stop(MedicationStatus.ACTIVE)
    with pytest.raises(AppError, match="ACTIVE"):
        assert_medication_can_stop(MedicationStatus.STOPPED)
    with pytest.raises(AppError, match="immutable"):
        assert_medication_mutable(MedicationStatus.ENTERED_IN_ERROR)
    with pytest.raises(AppError, match="immutable"):
        assert_medication_can_stop(MedicationStatus.ENTERED_IN_ERROR)


def test_pdp_allows_medication_permission_and_denies_unknown_allergy_alias() -> None:
    pdp = Wave1PolicyPDP()
    org_id = uuid4()
    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=(Permission.CLINICAL_MEDICATION_CREATE,),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Medication",
            action=Permission.CLINICAL_MEDICATION_CREATE,
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
            scopes=("clinical.procedure.create",),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Procedure",
            action="clinical.procedure.create",
            actor_organization_ids=(org_id,),
        )
    )
    assert unknown.allowed is False
    assert unknown.reason == "deny_by_default"
    unknown_dx = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=("clinical.diagnosis.create",),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Diagnosis",
            action="clinical.diagnosis.create",
            actor_organization_ids=(org_id,),
        )
    )
    assert unknown_dx.allowed is False
    assert unknown_dx.reason == "deny_by_default"


def test_medication_values_are_redacted_from_log_events() -> None:
    redacted = _redact_secrets(
        None,  # type: ignore[arg-type]
        "info",
        {
            "dose_numeric": "500",
            "dose_unit": "mg",
            "dose": "500 mg",
            "code_display": "Paracetamol",
            "event": "request",
        },
    )
    assert redacted["dose_numeric"] == "[REDACTED]"
    assert redacted["dose_unit"] == "[REDACTED]"
    assert redacted["dose"] == "[REDACTED]"
    assert redacted["code_display"] == "[REDACTED]"
    assert redacted["event"] == "request"
