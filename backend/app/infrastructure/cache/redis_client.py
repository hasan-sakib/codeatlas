from functools import lru_cache

from redis.asyncio import Redis


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    from app.core.config import get_settings

    # redis-py's from_url() is loosely typed (returns Any) despite always
    # returning a Redis instance at this call site.
    client: Redis = Redis.from_url(str(get_settings().redis.url), decode_responses=True)
    return client


def clear_redis_client_cache() -> None:
    """Test-only helper, mirrors app.core.config.clear_settings_cache."""
    get_redis_client.cache_clear()
