from collections.abc import Sequence
from typing import Protocol

from app.domain.value_objects.embedding_result import EmbeddingResult


class EmbeddingPort(Protocol):
    async def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingResult]:
        """Results are returned in the same order as `texts` — callers must
        not need to re-sort or zip by content to recover the mapping."""
        ...

    async def embed_query(self, text: str) -> EmbeddingResult: ...
