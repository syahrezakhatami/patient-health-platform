import pytest
from app.db.base import Base
from app.modules.audit.infrastructure.models import AuditEventModel
from app.modules.clinical.infrastructure.models import (
    ClinicalNoteModel,
    ClinicalProvenanceModel,
    EncounterModel,
    EncounterParticipantModel,
)
from app.modules.iam.infrastructure.models import UserModel
from app.modules.mpi.infrastructure.models import PatientIdentityModel
from app.modules.organization.infrastructure.models import OrganizationModel

pytestmark = pytest.mark.unit

FORBIDDEN_TABLES = {
    "diagnoses",
    "conditions",
    "medications",
    "prescriptions",
    "laboratory_results",
    "observations",
    "allergies",
    "vital_signs",
    "treatments",
    "care_plans",
    "imaging_studies",
    "clinical_timelines",
    "fhir_encounters",
    "fhir_patients",
}


def test_wave1_metadata_has_identity_tables_only() -> None:
    assert AuditEventModel.__tablename__ == "audit_events"
    assert UserModel.__tablename__ == "users"
    assert OrganizationModel.__tablename__ == "organizations"
    assert PatientIdentityModel.__tablename__ == "patient_identities"
    tables = set(Base.metadata.tables)
    assert tables.isdisjoint(FORBIDDEN_TABLES)
    assert "patient_identities" in tables
    assert "patient_identifiers" in tables
    assert "identity_merge_operations" in tables


def test_wave2a_metadata_has_foundation_tables_only() -> None:
    assert EncounterModel.__tablename__ == "encounters"
    assert EncounterParticipantModel.__tablename__ == "encounter_participants"
    assert ClinicalNoteModel.__tablename__ == "clinical_notes"
    assert ClinicalProvenanceModel.__tablename__ == "clinical_provenances"
    tables = set(Base.metadata.tables)
    assert tables.isdisjoint(FORBIDDEN_TABLES)
    foundation = {
        "encounters",
        "encounter_participants",
        "clinical_notes",
        "clinical_provenances",
    }
    assert foundation.issubset(tables)


def test_no_fhir_or_ai_modules_imported() -> None:
    import sys

    forbidden_prefixes = (
        "fhir",
        "openai",
        "langchain",
        "chromadb",
        "faiss",
    )
    loaded = {name.split(".")[0] for name in sys.modules}
    assert loaded.isdisjoint(set(forbidden_prefixes))
