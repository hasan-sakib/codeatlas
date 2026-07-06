from collections.abc import Mapping, Sequence

import pytest

from app.core.config import EmbeddingSettings
from app.domain.value_objects.embedding_result import EmbeddingResult
from app.infrastructure.embeddings import bge_m3_adapter as bma
from app.infrastructure.embeddings.bge_m3_adapter import BgeM3Adapter
from app.infrastructure.embeddings.text_normalizer import normalize_for_cache_key


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, EmbeddingResult] = {}
        self.get_many_calls: list[list[str]] = []
        self.set_many_calls: list[dict[str, EmbeddingResult]] = []

    async def get_many(self, keys: Sequence[str]) -> dict[str, EmbeddingResult]:
        self.get_many_calls.append(list(keys))
        return {key: self.store[key] for key in keys if key in self.store}

    async def set_many(self, entries: Mapping[str, EmbeddingResult], ttl_seconds: int) -> None:
        self.set_many_calls.append(dict(entries))
        self.store.update(entries)


def _settings(**overrides: object) -> EmbeddingSettings:
    defaults: dict[str, object] = {
        "model_id": "fake-model:v1",
        "batch_size": 2,
        "cache_ttl_seconds": 100,
    }
    defaults.update(overrides)
    return EmbeddingSettings(**defaults)  # type: ignore[arg-type]


def _fake_result(text: str, model_id: str) -> EmbeddingResult:
    return EmbeddingResult(dense=[float(len(text))] * 4, sparse={1: 0.5}, model_id=model_id)


@pytest.fixture(autouse=True)
def _stub_model_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test in this file should ever trigger a real (slow, network-
    dependent) BGE-M3 model load — only `_encode_sync` (mocked per test)
    is meant to stand in for the model boundary."""
    monkeypatch.setattr(BgeM3Adapter, "_load_model", lambda self: "fake-model-sentinel")


def _patch_encode(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_encode_sync(model: object, texts: list[str], model_id: str) -> list[EmbeddingResult]:
        calls.append(list(texts))
        return [_fake_result(text, model_id) for text in texts]

    monkeypatch.setattr(bma, "_encode_sync", fake_encode_sync)
    return calls


async def test_all_cache_hit_never_invokes_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    encode_calls = _patch_encode(monkeypatch)
    settings = _settings()
    cache = FakeCache()
    texts = ["alpha", "beta"]
    for text in texts:
        cache.store[normalize_for_cache_key(text, settings.model_id)] = _fake_result(
            text, settings.model_id
        )

    adapter = BgeM3Adapter(cache, settings)
    results = await adapter.embed_batch(texts)

    assert encode_calls == []
    assert [r.dense[0] for r in results] == [5.0, 4.0]


async def test_all_cache_miss_calls_model_and_writes_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    encode_calls = _patch_encode(monkeypatch)
    settings = _settings(batch_size=2)
    cache = FakeCache()
    adapter = BgeM3Adapter(cache, settings)

    results = await adapter.embed_batch(["a", "bb", "ccc"])

    assert encode_calls == [["a", "bb"], ["ccc"]]  # chunked by batch_size=2
    assert len(cache.set_many_calls) == 1
    assert len(cache.set_many_calls[0]) == 3
    assert [r.dense[0] for r in results] == [1.0, 2.0, 3.0]


async def test_preserves_input_order_across_mixed_hit_and_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encode_calls = _patch_encode(monkeypatch)
    settings = _settings()
    cache = FakeCache()
    cache.store[normalize_for_cache_key("aa", settings.model_id)] = _fake_result(
        "aa", settings.model_id
    )
    cache.store[normalize_for_cache_key("ccc", settings.model_id)] = _fake_result(
        "ccc", settings.model_id
    )

    adapter = BgeM3Adapter(cache, settings)
    results = await adapter.embed_batch(["aa", "b", "ccc"])

    assert [r.dense[0] for r in results] == [2.0, 1.0, 3.0]
    assert encode_calls == [["b"]]  # only the miss was ever sent to the model


async def test_respects_batch_size_when_chunking_a_large_miss_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encode_calls = _patch_encode(monkeypatch)
    settings = _settings(batch_size=32)
    adapter = BgeM3Adapter(FakeCache(), settings)

    texts = [f"text-{i}" for i in range(250)]
    await adapter.embed_batch(texts)

    assert [len(call) for call in encode_calls] == [32, 32, 32, 32, 32, 32, 32, 26]


async def test_embed_query_returns_a_single_result(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_encode(monkeypatch)
    adapter = BgeM3Adapter(FakeCache(), _settings())

    result = await adapter.embed_query("solo")

    assert result.dense[0] == 4.0


async def test_warm_up_runs_one_throwaway_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    encode_calls = _patch_encode(monkeypatch)
    adapter = BgeM3Adapter(FakeCache(), _settings())

    await adapter.warm_up()

    assert encode_calls == [["warm up"]]


def test_encode_sync_raises_on_wrong_dense_dimension() -> None:
    class _WrongShapeModel:
        def encode(
            self, texts: list[str], batch_size: int, return_dense: bool, return_sparse: bool
        ) -> dict[str, object]:
            return {
                "dense_vecs": [[0.1, 0.2, 0.3]],  # not EMBEDDING_DIM
                "lexical_weights": [{"1": 0.5}],
            }

    with pytest.raises(ValueError, match="1024"):
        bma._encode_sync(_WrongShapeModel(), ["text"], "model-id")  # type: ignore[arg-type]
