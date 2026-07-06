import pytest
from redis.asyncio import Redis

from app.core.config import EmbeddingSettings
from app.domain.value_objects.embedding_result import EmbeddingResult
from app.infrastructure.embeddings import bge_m3_adapter as bma
from app.infrastructure.embeddings.bge_m3_adapter import BgeM3Adapter
from app.infrastructure.embeddings.embedding_cache import RedisEmbeddingCache

pytestmark = pytest.mark.integration


def _fake_result(text: str, model_id: str) -> EmbeddingResult:
    return EmbeddingResult(dense=[float(len(text))] * 4, sparse={1: 0.5}, model_id=model_id)


async def test_cache_hit_rate_improves_across_overlapping_calls_against_real_redis(
    redis_client: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real Redis (testcontainers) end-to-end through the full adapter —
    only the ML inference itself is stubbed, so this proves the actual
    cache serialization/deserialization and hit/miss orchestration work
    against a real Redis instance, not just a fake. The real BGE-M3
    model was verified separately by hand during development (dense
    shape, sparse key/value types, warm_up/embed timing) — see
    docs/modules/embedding_pipeline.md — rather than baked into the
    checked-in suite, since it requires a ~2GB one-time download that
    would make every future CI run pay a cost unrelated to what changed.
    """
    monkeypatch.setattr(BgeM3Adapter, "_load_model", lambda self: "fake-model-sentinel")

    encode_calls: list[list[str]] = []

    def fake_encode_sync(model: object, texts: list[str], model_id: str) -> list[EmbeddingResult]:
        encode_calls.append(list(texts))
        return [_fake_result(text, model_id) for text in texts]

    monkeypatch.setattr(bma, "_encode_sync", fake_encode_sync)

    settings = EmbeddingSettings(model_id="bge-m3-integration-test:v1")
    cache = RedisEmbeddingCache(redis_client)
    adapter = BgeM3Adapter(cache, settings)

    first = await adapter.embed_batch(["alpha text", "beta text"])
    assert encode_calls == [["alpha text", "beta text"]]

    second = await adapter.embed_batch(["beta text", "gamma text"])
    assert encode_calls == [
        ["alpha text", "beta text"],
        ["gamma text"],
    ]  # "beta text" served from the real Redis cache, never re-embedded

    assert first[1] == second[0]  # identical EmbeddingResult round-tripped through real Redis
