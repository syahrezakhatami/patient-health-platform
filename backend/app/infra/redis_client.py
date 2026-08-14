from typing import TYPE_CHECKING

from redis.asyncio import Redis

from app.core.config import Settings

if TYPE_CHECKING:
    RedisClient = Redis[str]
else:
    RedisClient = Redis


def create_redis(settings: Settings) -> RedisClient:
    return Redis.from_url(
        settings.redis_url.get_secret_value(),
        decode_responses=True,
        health_check_interval=30,
    )


async def redis_ping(client: RedisClient) -> bool:
    return bool(await client.ping())
