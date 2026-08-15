import pytest
from app.db.base import Base
from app.modules.audit.infrastructure.models import AuditEventModel
from app.modules.clinical.infrastructure.models import (
    AllergyModel,
    ClinicalNoteModel,
    ClinicalProvenanceModel,
    ConditionModel,
    ConsentModel,
    EncounterModel,
    EncounterParticipantModel,
    ImmunizationModel,
    LaboratoryOrderModel,
    LaboratoryResultModel,
    LaboratorySpecimenModel,
    MedicalDeviceModel,
    MedicationModel,
    ObservationModel,
    ProcedureModel,
)
from app.modules.iam.infrastructure.models import UserModel
from app.modules.mpi.infrastructure.models import PatientIdentityModel
from app.modules.organization.infrastructure.models import OrganizationModel

pytestmark = pytest.mark.unit

FORBIDDEN_TABLES = {
    "diagnoses",
    "prescriptions",
    "vital_signs",
    "treatments",
    "care_plans",
    "imaging_studies",
    "clinical_timelines",
    "fhir_encounters",
    "fhir_patients",
    "fhir_observations",
    "fhir_specimens",
    "fhir_service_requests",
    "fhir_diagnostic_reports",
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


def test_wave2b1_metadata_has_conditions_without_later_clinical_domains() -> None:
    assert ConditionModel.__tablename__ == "conditions"
    tables = set(Base.metadata.tables)
    assert "conditions" in tables
    assert tables.isdisjoint(FORBIDDEN_TABLES)


def test_wave2b2a_metadata_has_observations_without_later_clinical_domains() -> None:
    assert ObservationModel.__tablename__ == "observations"
    tables = set(Base.metadata.tables)
    assert "observations" in tables
    assert "conditions" in tables
    assert tables.isdisjoint(FORBIDDEN_TABLES)


def test_wave2b2b_metadata_has_laboratory_without_later_clinical_domains() -> None:
    assert LaboratoryOrderModel.__tablename__ == "laboratory_orders"
    assert LaboratorySpecimenModel.__tablename__ == "laboratory_specimens"
    assert LaboratoryResultModel.__tablename__ == "laboratory_results"
    tables = set(Base.metadata.tables)
    assert {
        "laboratory_orders",
        "laboratory_specimens",
        "laboratory_results",
        "observations",
        "conditions",
    }.issubset(tables)
    assert tables.isdisjoint(FORBIDDEN_TABLES)


def test_wave2b3a_metadata_has_medications_without_later_clinical_domains() -> None:
    assert MedicationModel.__tablename__ == "medications"
    tables = set(Base.metadata.tables)
    assert {
        "medications",
        "laboratory_orders",
        "laboratory_specimens",
        "laboratory_results",
        "observations",
        "conditions",
    }.issubset(tables)
    assert tables.isdisjoint(FORBIDDEN_TABLES)


def test_wave2b3b_metadata_has_allergies_without_later_clinical_domains() -> None:
    assert AllergyModel.__tablename__ == "allergies"
    tables = set(Base.metadata.tables)
    assert {
        "allergies",
        "medications",
        "laboratory_orders",
        "laboratory_specimens",
        "laboratory_results",
        "observations",
        "conditions",
    }.issubset(tables)
    assert tables.isdisjoint(FORBIDDEN_TABLES)


def test_wave2b3c_metadata_has_consents_without_later_clinical_domains() -> None:
    assert ConsentModel.__tablename__ == "consents"
    tables = set(Base.metadata.tables)
    assert {
        "consents",
        "allergies",
        "medications",
        "laboratory_orders",
        "laboratory_specimens",
        "laboratory_results",
        "observations",
        "conditions",
    }.issubset(tables)
    assert tables.isdisjoint(FORBIDDEN_TABLES)
    assert "fhir_consents" not in tables


def test_wave2b4_metadata_has_immunizations_without_later_clinical_domains() -> None:
    assert ImmunizationModel.__tablename__ == "immunizations"
    tables = set(Base.metadata.tables)
    assert {
        "immunizations",
        "consents",
        "allergies",
        "medications",
        "laboratory_orders",
        "laboratory_specimens",
        "laboratory_results",
        "observations",
        "conditions",
    }.issubset(tables)
    assert tables.isdisjoint(FORBIDDEN_TABLES)
    assert "fhir_immunizations" not in tables
    assert "care_plans" not in tables


def test_wave2b5_metadata_has_procedures_without_later_clinical_domains() -> None:
    assert ProcedureModel.__tablename__ == "procedures"
    tables = set(Base.metadata.tables)
    assert {
        "procedures",
        "immunizations",
        "consents",
        "allergies",
        "medications",
        "laboratory_orders",
        "laboratory_specimens",
        "laboratory_results",
        "observations",
        "conditions",
    }.issubset(tables)
    assert tables.isdisjoint(FORBIDDEN_TABLES)
    assert "fhir_procedures" not in tables
    assert "care_plans" not in tables


def test_wave2b6_metadata_has_medical_devices_without_later_clinical_domains() -> None:
    assert MedicalDeviceModel.__tablename__ == "medical_devices"
    tables = set(Base.metadata.tables)
    assert {
        "medical_devices",
        "procedures",
        "immunizations",
        "consents",
        "allergies",
        "medications",
        "laboratory_orders",
        "laboratory_specimens",
        "laboratory_results",
        "observations",
        "conditions",
    }.issubset(tables)
    assert tables.isdisjoint(FORBIDDEN_TABLES)
    assert "fhir_devices" not in tables
    assert "fhir_medical_devices" not in tables
    assert "care_plans" not in tables
    assert "vital_signs" not in tables


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
