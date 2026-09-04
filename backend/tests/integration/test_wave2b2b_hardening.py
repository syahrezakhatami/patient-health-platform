import asyncio
import os
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import mint_token
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.db_privileges import PROVENANCE_DELETE_DENIED
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave2b2b_laboratory import (
    _collect_specimen,
    _lab_order,
    _open_lab_result,
)

pytestmark = [pytest.mark.integration]

APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


@requires_db
async def test_concurrent_order_cancel_versus_first_specimen(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id),
    )
    order_id = created.json()["id"]

    async def cancel() -> object:
        return await db_client.post(
            f"/api/v1/clinical/laboratory/orders/{order_id}/cancel",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    async def collect() -> object:
        return await _collect_specimen(db_client, clinician, order_id)

    left, right = await asyncio.gather(cancel(), collect())
    codes = {left.status_code, right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status FROM laboratory_orders WHERE id = :id"),
            {"id": order_id},
        )
        status = row.scalar_one()
        specimens = await connection.execute(
            text("SELECT count(*) FROM laboratory_specimens WHERE laboratory_order_id = :id"),
            {"id": order_id},
        )
        specimen_count = specimens.scalar_one()
        cancelled = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'LAB_ORDER_CANCELLED'
                """
            ),
            {"id": order_id},
        )
        progressed = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'LAB_ORDER_IN_PROGRESS'
                """
            ),
            {"id": order_id},
        )
    assert status in {"CANCELLED", "IN_PROGRESS"}
    if status == "CANCELLED":
        assert specimen_count == 0
        assert cancelled.scalar_one() == 1
        assert progressed.scalar_one() == 0
    else:
        assert specimen_count == 1
        assert cancelled.scalar_one() == 0
        assert progressed.scalar_one() == 1


@requires_db
async def test_concurrent_order_and_specimen_terminal_transitions(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    idle = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id),
    )
    idle_id = idle.json()["id"]

    async def cancel() -> object:
        return await db_client.post(
            f"/api/v1/clinical/laboratory/orders/{idle_id}/cancel",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    first, second = await asyncio.gather(cancel(), cancel())
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'LAB_ORDER_CANCELLED'
                """
            ),
            {"id": idle_id},
        )
        assert events.scalar_one() == 1

    order = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id),
    )
    specimen = await _collect_specimen(db_client, clinician, order.json()["id"])
    specimen_id = specimen.json()["id"]
    order_id = order.json()["id"]

    async def void_order() -> object:
        return await db_client.post(
            f"/api/v1/clinical/laboratory/orders/{order_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(void_order(), void_order())
    assert sorted([left.status_code, right.status_code]) == [200, 409]

    other = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id),
    )
    other_specimen = await _collect_specimen(db_client, clinician, other.json()["id"])
    other_id = other_specimen.json()["id"]

    async def reject() -> object:
        return await db_client.post(
            f"/api/v1/clinical/laboratory/specimens/{other_id}/reject",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    async def void_specimen() -> object:
        return await db_client.post(
            f"/api/v1/clinical/laboratory/specimens/{other_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    raced_left, raced_right = await asyncio.gather(reject(), void_specimen())
    raced_codes = {raced_left.status_code, raced_right.status_code}
    assert 200 in raced_codes
    assert raced_codes <= {200, 409}
    async with db_engine.connect() as connection:
        status = await connection.execute(
            text("SELECT status FROM laboratory_specimens WHERE id = :id"),
            {"id": other_id},
        )
        assert status.scalar_one() in {"REJECTED", "ENTERED_IN_ERROR"}
        assert specimen.json()["id"] == specimen_id


@requires_db
async def test_noop_order_and_specimen_transitions_do_not_duplicate_audit(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id),
    )
    order_id = created.json()["id"]
    cancelled = await db_client.post(
        f"/api/v1/clinical/laboratory/orders/{order_id}/cancel",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert cancelled.status_code == 200
    again = await db_client.post(
        f"/api/v1/clinical/laboratory/orders/{order_id}/cancel",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert again.status_code == 409
    eie_cancelled = await db_client.post(
        f"/api/v1/clinical/laboratory/orders/{order_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert eie_cancelled.status_code == 409

    open_order = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id),
    )
    specimen = await _collect_specimen(db_client, clinician, open_order.json()["id"])
    rejected = await db_client.post(
        f"/api/v1/clinical/laboratory/specimens/{specimen.json()['id']}/reject",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert rejected.status_code == 200
    reject_again = await db_client.post(
        f"/api/v1/clinical/laboratory/specimens/{specimen.json()['id']}/reject",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert reject_again.status_code == 409
    async with db_engine.connect() as connection:
        cancelled_events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'LAB_ORDER_CANCELLED'
                """
            ),
            {"id": order_id},
        )
        assert cancelled_events.scalar_one() == 1
        rejected_events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'LAB_SPECIMEN_REJECTED'
                """
            ),
            {"id": specimen.json()["id"]},
        )
        assert rejected_events.scalar_one() == 1


@requires_db
async def test_laboratory_unprovisioned_encounter_eie_and_delete_methods(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    org_admin = await seed_actor(
        db_engine, role_code=RoleCode.ORG_ADMIN, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    order, specimen, result = await _open_lab_result(db_client, clinician, patient_id)
    order_id = order.json()["id"]
    specimen_id = specimen.json()["id"]
    result_id = result.json()["id"]

    unprovisioned = mint_token(sub="nobody-laboratory")
    denied = await db_client.get(
        f"/api/v1/clinical/laboratory/orders/{order_id}",
        headers={
            "Authorization": f"Bearer {unprovisioned}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert denied.status_code == 403
    admin_create = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id),
    )
    assert admin_create.status_code == 403
    admin_read = await db_client.get(
        f"/api/v1/clinical/laboratory/orders/{order_id}",
        headers=org_admin.headers(purpose="TREATMENT"),
    )
    assert admin_read.status_code == 200

    type_change = await db_client.post(
        f"/api/v1/clinical/laboratory/results/{result_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"value_type": "TEXT", "value_text": "detected"},
    )
    assert type_change.status_code == 422

    for path in (
        f"/api/v1/clinical/laboratory/orders/{order_id}",
        f"/api/v1/clinical/laboratory/specimens/{specimen_id}",
        f"/api/v1/clinical/laboratory/results/{result_id}",
    ):
        deleted = await db_client.delete(path, headers=clinician.headers(purpose="TREATMENT"))
        assert deleted.status_code == 405
        put = await db_client.put(
            path,
            headers=clinician.headers(purpose="TREATMENT"),
            json={},
        )
        assert put.status_code == 405

    encounter = await _open_encounter(db_client, clinician, patient_id)
    void_encounter = await db_client.post(
        f"/api/v1/clinical/encounters/{encounter.json()['id']}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "ENTERED_IN_ERROR"},
    )
    assert void_encounter.status_code == 200
    blocked = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id, encounter.json()["id"]),
    )
    assert blocked.status_code == 409
    async with db_engine.connect() as connection:
        mutated = await connection.execute(
            text("SELECT status FROM encounters WHERE id = :id"),
            {"id": encounter.json()["id"]},
        )
        assert mutated.scalar_one() == "ENTERED_IN_ERROR"


@requires_db
async def test_laboratory_order_and_specimen_provenance_fk_and_app_dml(
    db_client, db_engine
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id),
    )
    order_id = created.json()["id"]
    specimen = await _collect_specimen(db_client, clinician, order_id)
    specimen_id = specimen.json()["id"]
    organization_id = clinician.organization_id
    async with db_engine.connect() as connection:
        order_prov = await connection.execute(
            text(
                """
                SELECT provenance_id, subject_type
                FROM laboratory_orders o
                JOIN clinical_provenances p ON p.id = o.provenance_id
                WHERE o.id = :id
                """
            ),
            {"id": order_id},
        )
        specimen_prov = await connection.execute(
            text(
                """
                SELECT provenance_id, subject_type
                FROM laboratory_specimens s
                JOIN clinical_provenances p ON p.id = s.provenance_id
                WHERE s.id = :id
                """
            ),
            {"id": specimen_id},
        )
        order_provenance_id, order_subject = order_prov.one()
        specimen_provenance_id, specimen_subject = specimen_prov.one()
        rules = await connection.execute(
            text(
                """
                SELECT rc.constraint_name, rc.delete_rule
                FROM information_schema.referential_constraints rc
                WHERE rc.constraint_name IN (
                    'fk_laboratory_orders_provenance_id',
                    'fk_laboratory_specimens_provenance_id'
                )
                ORDER BY rc.constraint_name
                """
            )
        )
        delete_rules = {row[0]: row[1] for row in rules}
    assert order_provenance_id is not None
    assert order_subject == "LABORATORY_ORDER"
    assert specimen_provenance_id is not None
    assert specimen_subject == "LABORATORY_SPECIMEN"
    assert delete_rules["fk_laboratory_orders_provenance_id"] == "RESTRICT"
    assert delete_rules["fk_laboratory_specimens_provenance_id"] == "RESTRICT"

    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="foreign key|fk_laboratory_orders_provenance"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO laboratory_orders (
                            id, patient_identity_id, organization_id, code_system, code,
                            status, ordered_at, version, provenance_id
                        ) VALUES (
                            :id, :patient_id, :organization_id, 'http://loinc.org', '24323-8',
                            'REGISTERED', now(), 1, :bad
                        )
                        """
                    ),
                    {
                        "id": uuid4(),
                        "patient_id": patient_id,
                        "organization_id": organization_id,
                        "bad": uuid4(),
                    },
                )
        with pytest.raises(Exception, match=PROVENANCE_DELETE_DENIED):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM clinical_provenances WHERE id = :id"),
                    {"id": order_provenance_id},
                )

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM laboratory_specimens WHERE id = :id"),
                        {"id": specimen_id},
                    )
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM laboratory_orders WHERE id = :id"),
                        {"id": order_id},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            "UPDATE laboratory_orders SET patient_identity_id = :pid WHERE id = :id"
                        ),
                        {"id": order_id, "pid": uuid4()},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            "UPDATE laboratory_specimens SET specimen_type = 'URINE' WHERE id = :id"
                        ),
                        {"id": specimen_id},
                    )
    finally:
        await engine.dispose()
