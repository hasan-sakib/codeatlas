from collections.abc import Sequence
from typing import Protocol

from app.domain.value_objects.embedding_result import EmbeddingResult


class EmbeddingPort(Protocol):
    async def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingResult]:
        """Results are returned in the same order as `texts` — callers must
        not need to re-sort or zip by content to recover the mapping."""
        ...

    async def embed_query(self, text: str) -> EmbeddingResult: ...

    async def warm_up(self) -> None:
        """Eagerly loads the underlying model, so the (potentially very
        slow) first-use cost is paid at process startup rather than on a
        real request — see app/main.py's lifespan."""
        ...
