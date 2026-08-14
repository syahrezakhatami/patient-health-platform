"""Permission catalog.

Authorization is permission-based, not ``if role == doctor``.
Wave 2B.2a adds observation permissions. Wave 2B.2b adds laboratory permissions.
Medication, allergy, and FHIR remain absent.
"""

from enum import StrEnum


class Permission(StrEnum):
    IAM_PLATFORM = "iam.platform"
    IAM_USER_READ = "iam.user.read"
    IAM_USER_PROVISION = "iam.user.provision"
    IAM_MEMBERSHIP_MANAGE = "iam.membership.manage"
    ORG_ORGANIZATION_CREATE = "org.organization.create"
    ORG_ORGANIZATION_READ = "org.organization.read"
    ORG_FACILITY_CREATE = "org.facility.create"
    ORG_FACILITY_READ = "org.facility.read"
    ORG_IDENTIFIER_MANAGE = "org.identifier.manage"
    MPI_IDENTITY_CREATE = "mpi.identity.create"
    MPI_IDENTITY_READ = "mpi.identity.read"
    MPI_IDENTIFIER_ADD = "mpi.identifier.add"
    MPI_IDENTIFIER_VERIFY = "mpi.identifier.verify"
    MPI_MATCH_EVALUATE = "mpi.match.evaluate"
    MPI_MATCH_REVIEW = "mpi.match.review"
    MPI_MERGE_EXECUTE = "mpi.merge.execute"
    MPI_UNMERGE_EXECUTE = "mpi.unmerge.execute"
    CLINICAL_ENCOUNTER_CREATE = "clinical.encounter.create"
    CLINICAL_ENCOUNTER_READ = "clinical.encounter.read"
    CLINICAL_ENCOUNTER_UPDATE_STATUS = "clinical.encounter.update_status"
    CLINICAL_NOTE_CREATE = "clinical.note.create"
    CLINICAL_NOTE_READ = "clinical.note.read"
    CLINICAL_NOTE_UPDATE_DRAFT = "clinical.note.update_draft"
    CLINICAL_NOTE_FINALIZE = "clinical.note.finalize"
    CLINICAL_CONDITION_CREATE = "clinical.condition.create"
    CLINICAL_CONDITION_READ = "clinical.condition.read"
    CLINICAL_CONDITION_UPDATE = "clinical.condition.update"
    CLINICAL_CONDITION_ENTERED_IN_ERROR = "clinical.condition.entered_in_error"
    CLINICAL_OBSERVATION_CREATE = "clinical.observation.create"
    CLINICAL_OBSERVATION_READ = "clinical.observation.read"
    CLINICAL_OBSERVATION_UPDATE = "clinical.observation.update"
    CLINICAL_OBSERVATION_ENTERED_IN_ERROR = "clinical.observation.entered_in_error"
    CLINICAL_LAB_ORDER_CREATE = "clinical.laboratory.order.create"
    CLINICAL_LAB_ORDER_READ = "clinical.laboratory.order.read"
    CLINICAL_LAB_ORDER_UPDATE = "clinical.laboratory.order.update"
    CLINICAL_LAB_ORDER_ENTERED_IN_ERROR = "clinical.laboratory.order.entered_in_error"
    CLINICAL_LAB_SPECIMEN_CREATE = "clinical.laboratory.specimen.create"
    CLINICAL_LAB_SPECIMEN_READ = "clinical.laboratory.specimen.read"
    CLINICAL_LAB_SPECIMEN_UPDATE = "clinical.laboratory.specimen.update"
    CLINICAL_LAB_SPECIMEN_ENTERED_IN_ERROR = "clinical.laboratory.specimen.entered_in_error"
    CLINICAL_LAB_RESULT_CREATE = "clinical.laboratory.result.create"
    CLINICAL_LAB_RESULT_READ = "clinical.laboratory.result.read"
    CLINICAL_LAB_RESULT_UPDATE = "clinical.laboratory.result.update"
    CLINICAL_LAB_RESULT_ENTERED_IN_ERROR = "clinical.laboratory.result.entered_in_error"


class RoleCode(StrEnum):
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    REGISTRAR = "REGISTRAR"
    IDENTITY_OFFICER = "IDENTITY_OFFICER"
    AUDITOR = "AUDITOR"
    CLINICIAN = "CLINICIAN"


WAVE2A_PERMISSIONS: frozenset[str] = frozenset(
    {
        Permission.CLINICAL_ENCOUNTER_CREATE,
        Permission.CLINICAL_ENCOUNTER_READ,
        Permission.CLINICAL_ENCOUNTER_UPDATE_STATUS,
        Permission.CLINICAL_NOTE_CREATE,
        Permission.CLINICAL_NOTE_READ,
        Permission.CLINICAL_NOTE_UPDATE_DRAFT,
        Permission.CLINICAL_NOTE_FINALIZE,
    }
)
WAVE2B1_PERMISSIONS: frozenset[str] = frozenset(
    {
        Permission.CLINICAL_CONDITION_CREATE,
        Permission.CLINICAL_CONDITION_READ,
        Permission.CLINICAL_CONDITION_UPDATE,
        Permission.CLINICAL_CONDITION_ENTERED_IN_ERROR,
    }
)
WAVE2B2A_PERMISSIONS: frozenset[str] = frozenset(
    {
        Permission.CLINICAL_OBSERVATION_CREATE,
        Permission.CLINICAL_OBSERVATION_READ,
        Permission.CLINICAL_OBSERVATION_UPDATE,
        Permission.CLINICAL_OBSERVATION_ENTERED_IN_ERROR,
    }
)
WAVE2B2B_PERMISSIONS: frozenset[str] = frozenset(
    {
        Permission.CLINICAL_LAB_ORDER_CREATE,
        Permission.CLINICAL_LAB_ORDER_READ,
        Permission.CLINICAL_LAB_ORDER_UPDATE,
        Permission.CLINICAL_LAB_ORDER_ENTERED_IN_ERROR,
        Permission.CLINICAL_LAB_SPECIMEN_CREATE,
        Permission.CLINICAL_LAB_SPECIMEN_READ,
        Permission.CLINICAL_LAB_SPECIMEN_UPDATE,
        Permission.CLINICAL_LAB_SPECIMEN_ENTERED_IN_ERROR,
        Permission.CLINICAL_LAB_RESULT_CREATE,
        Permission.CLINICAL_LAB_RESULT_READ,
        Permission.CLINICAL_LAB_RESULT_UPDATE,
        Permission.CLINICAL_LAB_RESULT_ENTERED_IN_ERROR,
    }
)
WAVE1_PERMISSIONS: frozenset[str] = (
    frozenset(item.value for item in Permission)
    - WAVE2A_PERMISSIONS
    - WAVE2B1_PERMISSIONS
    - WAVE2B2A_PERMISSIONS
    - WAVE2B2B_PERMISSIONS
)
CATALOG_PERMISSIONS: frozenset[str] = (
    WAVE1_PERMISSIONS
    | WAVE2A_PERMISSIONS
    | WAVE2B1_PERMISSIONS
    | WAVE2B2A_PERMISSIONS
    | WAVE2B2B_PERMISSIONS
)

# Canonical permission *definitions* and the seed map used by Alembic.
# Runtime assignment is read from role_permissions, not this dict.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    RoleCode.PLATFORM_ADMIN: CATALOG_PERMISSIONS,
    RoleCode.ORG_ADMIN: frozenset(
        {
            Permission.IAM_USER_READ,
            Permission.IAM_MEMBERSHIP_MANAGE,
            Permission.ORG_ORGANIZATION_READ,
            Permission.ORG_FACILITY_CREATE,
            Permission.ORG_FACILITY_READ,
            Permission.ORG_IDENTIFIER_MANAGE,
            Permission.MPI_IDENTITY_READ,
            Permission.CLINICAL_ENCOUNTER_READ,
            Permission.CLINICAL_NOTE_READ,
            Permission.CLINICAL_CONDITION_READ,
            Permission.CLINICAL_OBSERVATION_READ,
            Permission.CLINICAL_LAB_ORDER_READ,
            Permission.CLINICAL_LAB_SPECIMEN_READ,
            Permission.CLINICAL_LAB_RESULT_READ,
        }
    ),
    RoleCode.REGISTRAR: frozenset(
        {
            Permission.IAM_USER_READ,
            Permission.ORG_ORGANIZATION_READ,
            Permission.ORG_FACILITY_READ,
            Permission.MPI_IDENTITY_CREATE,
            Permission.MPI_IDENTITY_READ,
            Permission.MPI_IDENTIFIER_ADD,
            Permission.MPI_MATCH_EVALUATE,
            Permission.CLINICAL_ENCOUNTER_CREATE,
            Permission.CLINICAL_ENCOUNTER_READ,
        }
    ),
    RoleCode.IDENTITY_OFFICER: frozenset(
        {
            Permission.IAM_USER_READ,
            Permission.ORG_ORGANIZATION_READ,
            Permission.ORG_FACILITY_READ,
            Permission.MPI_IDENTITY_CREATE,
            Permission.MPI_IDENTITY_READ,
            Permission.MPI_IDENTIFIER_ADD,
            Permission.MPI_IDENTIFIER_VERIFY,
            Permission.MPI_MATCH_EVALUATE,
            Permission.MPI_MATCH_REVIEW,
            Permission.MPI_MERGE_EXECUTE,
            Permission.MPI_UNMERGE_EXECUTE,
        }
    ),
    RoleCode.AUDITOR: frozenset(
        {
            Permission.IAM_USER_READ,
            Permission.ORG_ORGANIZATION_READ,
            Permission.ORG_FACILITY_READ,
            Permission.MPI_IDENTITY_READ,
            Permission.CLINICAL_ENCOUNTER_READ,
            Permission.CLINICAL_NOTE_READ,
            Permission.CLINICAL_CONDITION_READ,
            Permission.CLINICAL_OBSERVATION_READ,
            Permission.CLINICAL_LAB_ORDER_READ,
            Permission.CLINICAL_LAB_SPECIMEN_READ,
            Permission.CLINICAL_LAB_RESULT_READ,
        }
    ),
    RoleCode.CLINICIAN: frozenset(
        {
            Permission.IAM_USER_READ,
            Permission.ORG_ORGANIZATION_READ,
            Permission.ORG_FACILITY_READ,
            Permission.MPI_IDENTITY_READ,
            Permission.CLINICAL_ENCOUNTER_CREATE,
            Permission.CLINICAL_ENCOUNTER_READ,
            Permission.CLINICAL_ENCOUNTER_UPDATE_STATUS,
            Permission.CLINICAL_NOTE_CREATE,
            Permission.CLINICAL_NOTE_READ,
            Permission.CLINICAL_NOTE_UPDATE_DRAFT,
            Permission.CLINICAL_NOTE_FINALIZE,
            Permission.CLINICAL_CONDITION_CREATE,
            Permission.CLINICAL_CONDITION_READ,
            Permission.CLINICAL_CONDITION_UPDATE,
            Permission.CLINICAL_CONDITION_ENTERED_IN_ERROR,
            Permission.CLINICAL_OBSERVATION_CREATE,
            Permission.CLINICAL_OBSERVATION_READ,
            Permission.CLINICAL_OBSERVATION_UPDATE,
            Permission.CLINICAL_OBSERVATION_ENTERED_IN_ERROR,
            Permission.CLINICAL_LAB_ORDER_CREATE,
            Permission.CLINICAL_LAB_ORDER_READ,
            Permission.CLINICAL_LAB_ORDER_UPDATE,
            Permission.CLINICAL_LAB_ORDER_ENTERED_IN_ERROR,
            Permission.CLINICAL_LAB_SPECIMEN_CREATE,
            Permission.CLINICAL_LAB_SPECIMEN_READ,
            Permission.CLINICAL_LAB_SPECIMEN_UPDATE,
            Permission.CLINICAL_LAB_SPECIMEN_ENTERED_IN_ERROR,
            Permission.CLINICAL_LAB_RESULT_CREATE,
            Permission.CLINICAL_LAB_RESULT_READ,
            Permission.CLINICAL_LAB_RESULT_UPDATE,
            Permission.CLINICAL_LAB_RESULT_ENTERED_IN_ERROR,
        }
    ),
}

ORG_SCOPED_PERMISSIONS: frozenset[str] = (CATALOG_PERMISSIONS) - frozenset(
    {
        Permission.IAM_PLATFORM,
        Permission.IAM_USER_READ,
        Permission.IAM_USER_PROVISION,
        Permission.ORG_ORGANIZATION_CREATE,
    }
)
