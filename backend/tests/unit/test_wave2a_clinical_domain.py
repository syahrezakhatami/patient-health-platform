from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.core.logging import _redact_secrets
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.clinical.domain.enums import ClinicalRecordStatus, EncounterStatus
from app.modules.clinical.domain.lifecycle import (
    assert_encounter_transition,
    assert_note_can_finalize,
    assert_note_is_draft,
)
from app.modules.clinical.domain.terminology import parse_codeable_concept
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


def test_encounter_rejects_illegal_transitions() -> None:
    with pytest.raises(AppError, match="cannot transition"):
        assert_encounter_transition(EncounterStatus.FINISHED, EncounterStatus.IN_PROGRESS)
    with pytest.raises(AppError, match="cannot transition"):
        assert_encounter_transition(EncounterStatus.CANCELLED, EncounterStatus.IN_PROGRESS)
    with pytest.raises(AppError, match="cannot transition"):
        assert_encounter_transition(EncounterStatus.ENTERED_IN_ERROR, EncounterStatus.FINISHED)
    assert_encounter_transition(EncounterStatus.PLANNED, EncounterStatus.IN_PROGRESS)
    assert_encounter_transition(EncounterStatus.PLANNED, EncounterStatus.CANCELLED)
    assert_encounter_transition(EncounterStatus.IN_PROGRESS, EncounterStatus.FINISHED)
    assert_encounter_transition(EncounterStatus.IN_PROGRESS, EncounterStatus.CANCELLED)
    assert_encounter_transition(EncounterStatus.FINISHED, EncounterStatus.ENTERED_IN_ERROR)
    assert "COMPLETED" not in {item.value for item in EncounterStatus}


def test_final_note_cannot_be_edited() -> None:
    with pytest.raises(AppError, match="DRAFT"):
        assert_note_is_draft(ClinicalRecordStatus.FINAL)
    with pytest.raises(AppError, match="DRAFT"):
        assert_note_can_finalize(ClinicalRecordStatus.FINAL)


def test_terminology_stub_requires_system_and_code() -> None:
    assert parse_codeable_concept(None) is None
    with pytest.raises(AppError, match="system and code"):
        parse_codeable_concept({"system": "http://example.org", "code": ""})
    concept = parse_codeable_concept(
        {"system": "http://example.org/reason", "code": "ED", "display": "Emergency"}
    )
    assert concept is not None
    assert concept.code == "ED"


def test_pdp_allows_catalogued_clinical_permission_and_denies_unknown() -> None:
    pdp = Wave1PolicyPDP()
    org_id = uuid4()
    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=(Permission.CLINICAL_ENCOUNTER_CREATE,),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Encounter",
            action=Permission.CLINICAL_ENCOUNTER_CREATE,
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
            scopes=("clinical.diagnosis.create",),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Diagnosis",
            action="clinical.diagnosis.create",
            actor_organization_ids=(org_id,),
        )
    )
    assert unknown.allowed is False
    assert unknown.reason == "deny_by_default"


def test_note_body_is_redacted_from_log_events() -> None:
    redacted = _redact_secrets(
        None,  # type: ignore[arg-type]
        "info",
        {"body_text": "patient reported chest pain", "event": "request"},
    )
    assert redacted["body_text"] == "[REDACTED]"
    assert redacted["event"] == "request"
