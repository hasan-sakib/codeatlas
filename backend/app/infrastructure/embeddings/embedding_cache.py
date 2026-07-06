import json
from collections.abc import Mapping, Sequence
from typing import Protocol

from redis.asyncio import Redis

from app.domain.value_objects.embedding_result import EmbeddingResult

_KEY_PREFIX = "embedding:cache:"


class EmbeddingCachePort(Protocol):
    async def get_many(self, keys: Sequence[str]) -> dict[str, EmbeddingResult]: ...
    async def set_many(self, entries: Mapping[str, EmbeddingResult], ttl_seconds: int) -> None: ...


class RedisEmbeddingCache(EmbeddingCachePort):
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_many(self, keys: Sequence[str]) -> dict[str, EmbeddingResult]:
        if not keys:
            return {}
        raw_values = await self._redis.mget([f"{_KEY_PREFIX}{key}" for key in keys])
        results: dict[str, EmbeddingResult] = {}
        for key, raw in zip(keys, raw_values, strict=True):
            if raw is not None:
                results[key] = _deserialize(raw)
        return results

    async def set_many(self, entries: Mapping[str, EmbeddingResult], ttl_seconds: int) -> None:
        if not entries:
            return
        pipe = self._redis.pipeline(transaction=False)
        for key, result in entries.items():
            pipe.setex(f"{_KEY_PREFIX}{key}", ttl_seconds, _serialize(result))
        await pipe.execute()


def _serialize(result: EmbeddingResult) -> str:
    return json.dumps({"dense": result.dense, "sparse": result.sparse, "model_id": result.model_id})


def _deserialize(raw: str) -> EmbeddingResult:
    payload = json.loads(raw)
    return EmbeddingResult(
        dense=payload["dense"],
        sparse={int(token_id): weight for token_id, weight in payload["sparse"].items()},
        model_id=payload["model_id"],
    )
