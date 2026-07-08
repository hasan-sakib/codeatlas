import asyncio
from collections.abc import Sequence

import structlog
import torch
from FlagEmbedding import BGEM3FlagModel

from app.core.config import EmbeddingSettings
from app.core.constants import EMBEDDING_DIM
from app.domain.value_objects.embedding_result import EmbeddingResult
from app.infrastructure.embeddings.embedding_cache import EmbeddingCachePort
from app.infrastructure.embeddings.text_normalizer import normalize_for_cache_key

logger = structlog.get_logger(__name__)


class BgeM3Adapter:
    """`EmbeddingPort` backed by BGE-M3 (dense + sparse in one model, via
    the FlagEmbedding library — the only wrapper that exposes BGE-M3's
    sparse/lexical-weight head, not just a generic sentence-embedding
    interface). The model is loaded once, lazily, on first real use
    (guarded by a lock so concurrent callers don't each trigger their own
    load) — call `warm_up()` explicitly at process startup to pay that
    cost before real traffic arrives instead.
    """

    def __init__(self, cache: EmbeddingCachePort, settings: EmbeddingSettings) -> None:
        self._cache = cache
        self._settings = settings
        self._model: BGEM3FlagModel | None = None
        self._model_lock = asyncio.Lock()

    async def warm_up(self) -> None:
        model = await self._ensure_model()
        await asyncio.to_thread(_encode_sync, model, ["warm up"], self._settings.model_id)

    async def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingResult]:
        if not texts:
            return []

        keys = [normalize_for_cache_key(text, self._settings.model_id) for text in texts]
        cached = await self._cache.get_many(keys)

        miss_indices = [i for i, key in enumerate(keys) if key not in cached]
        if miss_indices:
            miss_texts = [texts[i] for i in miss_indices]
            newly_embedded = await self._embed_uncached(miss_texts)
            to_cache = {
                keys[i]: result for i, result in zip(miss_indices, newly_embedded, strict=True)
            }
            await self._cache.set_many(to_cache, self._settings.cache_ttl_seconds)
            cached.update(to_cache)

        return [cached[key] for key in keys]

    async def embed_query(self, text: str) -> EmbeddingResult:
        # A single-element embed_batch call already is "skip batching,
        # embed immediately" — embed_batch never waits to accumulate a
        # fuller batch across calls, so there's no separate fast path to
        # write here without duplicating the cache-then-model flow.
        (result,) = await self.embed_batch([text])
        return result

    async def _embed_uncached(self, texts: list[str]) -> list[EmbeddingResult]:
        model = await self._ensure_model()
        batch_size = self._settings.batch_size
        results: list[EmbeddingResult] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            results.extend(
                await asyncio.to_thread(_encode_sync, model, batch, self._settings.model_id)
            )
        return results

    async def _ensure_model(self) -> BGEM3FlagModel:
        if self._model is None:
            async with self._model_lock:
                if self._model is None:  # re-check: lost the race while awaiting the lock
                    self._model = await asyncio.to_thread(self._load_model)
        return self._model

    def _load_model(self) -> BGEM3FlagModel:
        # fp16 matmul on CPU is unreliable (many CPU BLAS kernels don't
        # properly support it) and was observed to silently produce
        # all-NaN embeddings in a CPU-only container — verified directly:
        # the exact same EMBEDDING__USE_FP16=true setting is harmless on
        # a host with a CUDA-capable GPU but corrupts every embedding
        # without raising when no CUDA device is present. Never trust the
        # config flag alone; gate it on real hardware support.
        use_fp16 = self._settings.use_fp16 and torch.cuda.is_available()
        if self._settings.use_fp16 and not use_fp16:
            logger.warning(
                "embedding.fp16_disabled_no_cuda",
                detail=(
                    "EMBEDDING__USE_FP16=true but no CUDA device is available; "
                    "falling back to fp32 to avoid silently corrupting embeddings."
                ),
            )
        return BGEM3FlagModel(self._settings.model_name_or_path, use_fp16=use_fp16)


def _encode_sync(model: BGEM3FlagModel, texts: list[str], model_id: str) -> list[EmbeddingResult]:
    output = model.encode(texts, batch_size=len(texts), return_dense=True, return_sparse=True)
    dense_vecs = output["dense_vecs"]
    lexical_weights = output["lexical_weights"]

    results: list[EmbeddingResult] = []
    for i in range(len(texts)):
        dense = [float(x) for x in dense_vecs[i]]
        if len(dense) != EMBEDDING_DIM:
            raise ValueError(
                f"Expected a {EMBEDDING_DIM}-dim dense vector from BGE-M3, got {len(dense)}"
            )
        sparse = {int(token_id): float(weight) for token_id, weight in lexical_weights[i].items()}
        results.append(EmbeddingResult(dense=dense, sparse=sparse, model_id=model_id))
    return results
