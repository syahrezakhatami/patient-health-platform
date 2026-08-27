from uuid import uuid4

from sqlalchemy import text
from tests.integration.conftest import SeededActor


def new_idempotency_key(prefix: str = "note") -> str:
    return f"{prefix}-{uuid4().hex}"


def note_write_headers(
    actor: SeededActor,
    *,
    purpose: str = "TREATMENT",
    idempotency_key: str | None = None,
    facility_id: object | None = None,
) -> dict[str, str]:
    headers = actor.headers(purpose=purpose)
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    if facility_id is not None:
        headers["X-Facility-Id"] = str(facility_id)
    return headers


def create_note_body(
    patient_id: object,
    encounter_id: object,
    *,
    note_type: str = "PROGRESS",
    body_text: str = "Clinical assessment.",
) -> dict[str, object]:
    return {
        "expected_patient_identity_id": str(patient_id),
        "encounter_id": str(encounter_id),
        "note_type": note_type,
        "body_text": body_text,
    }


def update_note_body(
    patient_id: object,
    expected_version: int,
    body_text: str,
) -> dict[str, object]:
    return {
        "expected_patient_identity_id": str(patient_id),
        "expected_version": expected_version,
        "body_text": body_text,
    }


def finalize_note_body(patient_id: object) -> dict[str, object]:
    return {"expected_patient_identity_id": str(patient_id)}


async def restore_note_write_idempotency_app_dml_privileges(db_engine) -> None:
    """Match scripts/grant_dev_privileges.sql after Alembic recreates the table."""
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE "
                "clinical_note_write_idempotency FROM app_dml"
            )
        )
        await connection.execute(
            text("GRANT INSERT, SELECT ON TABLE clinical_note_write_idempotency TO app_dml")
        )
