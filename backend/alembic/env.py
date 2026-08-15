import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.base import Base
from app.modules.audit.infrastructure.models import AuditEventModel
from app.modules.iam.infrastructure.models import (
    OrganizationMembershipModel,
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
)
from app.modules.clinical.infrastructure.models import (
    ClinicalNoteModel,
    ClinicalProvenanceModel,
    ConditionModel,
    EncounterModel,
    EncounterParticipantModel,
    LaboratoryOrderModel,
    LaboratoryResultModel,
    LaboratorySpecimenModel,
    AllergyModel,
    ConsentModel,
    MedicationModel,
    ObservationModel,
)
from app.modules.mpi.infrastructure.models import (
    IdentityClusterMemberModel,
    IdentityClusterModel,
    IdentityMatchCandidateModel,
    IdentityMatchProbeModel,
    IdentityMergeOperationModel,
    IdentityProvenanceModel,
    PatientIdentifierModel,
    PatientIdentityModel,
)
from app.modules.organization.infrastructure.models import (
    FacilityModel,
    OrganizationIdentifierModel,
    OrganizationModel,
)

assert AuditEventModel.__tablename__ == "audit_events"
assert UserModel.__tablename__ == "users"
assert RoleModel.__tablename__ == "roles"
assert PermissionModel.__tablename__ == "permissions"
assert RolePermissionModel.__tablename__ == "role_permissions"
assert OrganizationMembershipModel.__tablename__ == "organization_memberships"
assert OrganizationModel.__tablename__ == "organizations"
assert FacilityModel.__tablename__ == "facilities"
assert OrganizationIdentifierModel.__tablename__ == "organization_identifiers"
assert PatientIdentityModel.__tablename__ == "patient_identities"
assert PatientIdentifierModel.__tablename__ == "patient_identifiers"
assert IdentityClusterModel.__tablename__ == "identity_clusters"
assert IdentityClusterMemberModel.__tablename__ == "identity_cluster_members"
assert IdentityMatchCandidateModel.__tablename__ == "identity_match_candidates"
assert IdentityMatchProbeModel.__tablename__ == "identity_match_probes"
assert IdentityMergeOperationModel.__tablename__ == "identity_merge_operations"
assert IdentityProvenanceModel.__tablename__ == "identity_provenances"
assert EncounterModel.__tablename__ == "encounters"
assert EncounterParticipantModel.__tablename__ == "encounter_participants"
assert ClinicalNoteModel.__tablename__ == "clinical_notes"
assert ClinicalProvenanceModel.__tablename__ == "clinical_provenances"
assert ConditionModel.__tablename__ == "conditions"
assert ObservationModel.__tablename__ == "observations"
assert LaboratoryOrderModel.__tablename__ == "laboratory_orders"
assert LaboratorySpecimenModel.__tablename__ == "laboratory_specimens"
assert LaboratoryResultModel.__tablename__ == "laboratory_results"
assert MedicationModel.__tablename__ == "medications"
assert AllergyModel.__tablename__ == "allergies"
assert ConsentModel.__tablename__ == "consents"

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
migration_url = (
    settings.database_migration_url.get_secret_value()
    if settings.database_migration_url is not None
    else settings.database_url.get_secret_value()
)
config.set_main_option("sqlalchemy.url", migration_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=migration_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
