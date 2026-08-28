import os

import pytest
from app.core.config import Settings
from app.infra.redis_client import create_redis, redis_ping
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
REDIS_URL = os.environ.get("TEST_REDIS_URL") or os.environ.get("REDIS_URL")


requires_db = pytest.mark.skipif(
    not DATABASE_URL,
    reason="TEST_DATABASE_URL or DATABASE_URL is required for integration tests",
)
requires_redis = pytest.mark.skipif(
    not REDIS_URL,
    reason="TEST_REDIS_URL or REDIS_URL is required for integration tests",
)


@requires_db
async def test_postgres_connectivity() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        await engine.dispose()


@requires_redis
async def test_redis_connectivity() -> None:
    settings = Settings(redis_url=REDIS_URL)  # type: ignore[arg-type]
    client = create_redis(settings)
    try:
        assert await redis_ping(client) is True
    finally:
        await client.aclose()


@requires_db
async def test_audit_events_table_is_insert_only() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    insert_sql = """
        INSERT INTO audit_events (
            id, action, resource_type, result, occurred_at, metadata
        ) VALUES (
            gen_random_uuid(),
            'test.probe',
            'Platform',
            'SUCCESS',
            now(),
            '{"synthetic":"true"}'::jsonb
        )
    """
    try:
        async with engine.connect() as connection:
            exists = await connection.execute(text("SELECT to_regclass('public.audit_events')"))
            if exists.scalar_one() is None:
                pytest.skip("audit_events table is not migrated yet")
        async with engine.begin() as connection:
            await connection.execute(text(insert_sql))
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="insert-only|permission denied"):
                await connection.execute(text("UPDATE audit_events SET action = 'x'"))
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="insert-only|permission denied"):
                await connection.execute(text("DELETE FROM audit_events"))
    finally:
        await engine.dispose()
