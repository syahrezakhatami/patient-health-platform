from uuid import UUID

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from tests.integration.conftest import requires_db, seed_actor

pytestmark = pytest.mark.integration


@requires_db
async def test_platform_admin_can_create_organization_and_facility(db_client, db_engine) -> None:
    admin = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    created = await db_client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {admin.token}"},
        json={
            "name": "City Clinic",
            "code": f"CLINIC{admin.user_id.hex[:6]}",
            "organization_type": "CLINIC",
        },
    )
    assert created.status_code in {200, 201}
    assert created.json()["organization_type"] == "CLINIC"
    organization_id = created.json()["id"]
    facility = await db_client.post(
        f"/api/v1/organizations/{organization_id}/facilities",
        headers={
            "Authorization": f"Bearer {admin.token}",
            "X-Organization-Id": organization_id,
        },
        json={
            "name": "Main Site",
            "code": "MAIN",
            "facility_type": "CLINIC_SITE",
            "address_text": "Jl. Kesehatan 1",
        },
    )
    assert facility.status_code == 403
    identifier = await db_client.post(
        f"/api/v1/organizations/{organization_id}/identifiers",
        headers={
            "Authorization": f"Bearer {admin.token}",
            "X-Organization-Id": organization_id,
        },
        json={
            "identifier_system": "id.provider",
            "identifier_value": f"PRV-{admin.user_id.hex[:8]}",
        },
    )
    assert identifier.status_code == 403
    org_admin = await seed_actor(
        db_engine, role_code=RoleCode.ORG_ADMIN, organization_id=UUID(organization_id)
    )
    tenant_facility = await db_client.post(
        f"/api/v1/organizations/{organization_id}/facilities",
        headers={
            "Authorization": f"Bearer {org_admin.token}",
            "X-Organization-Id": organization_id,
        },
        json={
            "name": "Main Site",
            "code": "MAIN",
            "facility_type": "CLINIC_SITE",
            "address_text": "Jl. Kesehatan 1",
        },
    )
    assert tenant_facility.status_code in {200, 201}
