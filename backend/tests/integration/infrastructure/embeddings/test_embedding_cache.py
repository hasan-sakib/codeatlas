import pytest
from redis.asyncio import Redis

from app.domain.value_objects.embedding_result import EmbeddingResult
from app.infrastructure.embeddings.embedding_cache import RedisEmbeddingCache

pytestmark = pytest.mark.integration


async def test_get_many_on_empty_cache_returns_empty_dict(redis_client: Redis) -> None:
    cache = RedisEmbeddingCache(redis_client)

    result = await cache.get_many(["missing-key-1", "missing-key-2"])

    assert result == {}


async def test_get_many_with_no_keys_returns_empty_dict(redis_client: Redis) -> None:
    cache = RedisEmbeddingCache(redis_client)

    assert await cache.get_many([]) == {}


async def test_set_many_then_get_many_round_trips_full_fidelity(redis_client: Redis) -> None:
    cache = RedisEmbeddingCache(redis_client)
    result = EmbeddingResult(
        dense=[0.1, 0.2, 0.3], sparse={10: 0.5, 200: 0.25}, model_id="bge-m3:v1"
    )

    await cache.set_many({"key-a": result}, ttl_seconds=60)
    fetched = await cache.get_many(["key-a", "key-missing"])

    assert fetched == {"key-a": result}
    assert fetched["key-a"].sparse == {10: 0.5, 200: 0.25}  # int keys survive the JSON round-trip


async def test_set_many_applies_the_given_ttl(redis_client: Redis) -> None:
    cache = RedisEmbeddingCache(redis_client)
    result = EmbeddingResult(dense=[1.0], sparse={}, model_id="m")

    await cache.set_many({"key-ttl": result}, ttl_seconds=60)

    ttl = await redis_client.ttl("embedding:cache:key-ttl")
    assert 0 < ttl <= 60
