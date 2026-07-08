import asyncio
from dataclasses import replace

import structlog

from app.domain.value_objects.ranked_chunk import RankedChunk
from app.infrastructure.reranker.model_registry import get_cross_encoder

logger = structlog.get_logger(__name__)

# Rough, deliberately generous heuristic (no tokenizer call needed just to
# estimate a truncation point) — the model's own tokenizer still enforces
# the real token-level max_length as a backstop. This exists so the
# *chunk* side of the pair gets shortened preferentially; the default
# pair-truncation strategy a tokenizer applies (e.g. "longest_first")
# could otherwise cut into the query instead.
_APPROX_CHARS_PER_TOKEN = 4


class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str,
        max_length: int = 512,
        batch_size: int = 16,
        device: str = "cpu",
        fail_open: bool = True,
    ) -> None:
        self._model_name = model_name
        self._max_length = max_length
        self._batch_size = batch_size
        self._device = device
        self._fail_open = fail_open

    async def score(self, query: str, chunks: list[RankedChunk]) -> list[RankedChunk]:
        if not chunks:
            return []

        pairs = [(query, _truncate(chunk.text or "", self._max_length)) for chunk in chunks]

        try:
            scores = await asyncio.to_thread(self._predict_batch, pairs)
        except Exception:
            if not self._fail_open:
                raise
            logger.warning(
                "reranker.failed_fail_open",
                model_name=self._model_name,
                chunk_count=len(chunks),
                detail="returning input order unchanged",
            )
            return list(chunks)

        reranked = [
            replace(chunk, score=score, source="reranked")
            for chunk, score in zip(chunks, scores, strict=True)
        ]
        reranked.sort(key=lambda c: c.score, reverse=True)
        return reranked

    def _predict_batch(self, pairs: list[tuple[str, str]]) -> list[float]:
        model = get_cross_encoder(self._model_name, self._max_length, self._device)
        scores = model.predict(pairs, batch_size=self._batch_size)
        return [float(s) for s in scores]


def _truncate(text: str, max_length: int) -> str:
    max_chars = max_length * _APPROX_CHARS_PER_TOKEN
    return text if len(text) <= max_chars else text[:max_chars]
