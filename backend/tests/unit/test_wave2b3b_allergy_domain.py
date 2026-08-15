from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.core.logging import _redact_secrets
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.clinical.application.services import _parse_optional_reaction
from app.modules.clinical.domain.enums import AllergyStatus
from app.modules.clinical.domain.lifecycle import (
    ALLERGY_TRANSITIONS,
    assert_allergy_can_amend,
    assert_allergy_mutable,
)
from app.modules.clinical.domain.terminology import CodeableConcept
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


def test_allergy_reaction_requires_both_or_neither() -> None:
    assert _parse_optional_reaction(None) == (None, None, None)
    assert _parse_optional_reaction(
        CodeableConcept(system="http://snomed.info/sct", code="39579001", display="Anaphylaxis")
    ) == ("http://snomed.info/sct", "39579001", "Anaphylaxis")
    with pytest.raises(AppError, match="system and code"):
        _parse_optional_reaction(CodeableConcept(system=" ", code="39579001", display=None))
    with pytest.raises(AppError, match="system and code"):
        _parse_optional_reaction(
            CodeableConcept(system="http://snomed.info/sct", code=" ", display=None)
        )


def test_allergy_lifecycle_and_immutability() -> None:
    assert AllergyStatus.AMENDED in ALLERGY_TRANSITIONS[AllergyStatus.ACTIVE]
    assert AllergyStatus.ENTERED_IN_ERROR in ALLERGY_TRANSITIONS[AllergyStatus.ACTIVE]
    assert AllergyStatus.ENTERED_IN_ERROR in ALLERGY_TRANSITIONS[AllergyStatus.AMENDED]
    assert ALLERGY_TRANSITIONS[AllergyStatus.ENTERED_IN_ERROR] == frozenset()
    assert_allergy_can_amend(AllergyStatus.ACTIVE)
    assert_allergy_can_amend(AllergyStatus.AMENDED)
    with pytest.raises(AppError, match="immutable"):
        assert_allergy_mutable(AllergyStatus.ENTERED_IN_ERROR)
    with pytest.raises(AppError, match="immutable"):
        assert_allergy_can_amend(AllergyStatus.ENTERED_IN_ERROR)


def test_pdp_allows_allergy_permission_and_denies_unknown_consent_alias() -> None:
    pdp = Wave1PolicyPDP()
    org_id = uuid4()
    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=(Permission.CLINICAL_ALLERGY_CREATE,),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Allergy",
            action=Permission.CLINICAL_ALLERGY_CREATE,
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
            scopes=("clinical.care_plan.create",),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="CarePlan",
            action="clinical.care_plan.create",
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


def test_allergy_values_are_redacted_from_log_events() -> None:
    redacted = _redact_secrets(
        None,  # type: ignore[arg-type]
        "info",
        {
            "code_display": "Penicillin",
            "reaction": "Anaphylaxis",
            "reaction_display": "Anaphylaxis",
            "reaction_code": "39579001",
            "reaction_code_system": "http://snomed.info/sct",
            "severity": "SEVERE",
            "criticality": "HIGH",
            "event": "request",
        },
    )
    assert redacted["code_display"] == "[REDACTED]"
    assert redacted["reaction"] == "[REDACTED]"
    assert redacted["reaction_display"] == "[REDACTED]"
    assert redacted["reaction_code"] == "[REDACTED]"
    assert redacted["reaction_code_system"] == "[REDACTED]"
    assert redacted["severity"] == "[REDACTED]"
    assert redacted["criticality"] == "[REDACTED]"
    assert redacted["event"] == "request"
