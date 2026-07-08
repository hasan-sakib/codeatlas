from typing import Protocol

from app.domain.value_objects.ranked_chunk import RankedChunk


class RerankerPort(Protocol):
    async def score(self, query: str, chunks: list[RankedChunk]) -> list[RankedChunk]:
        """Returns `chunks` re-ordered by relevance score, descending.
        Does not slice to any particular N — that decision belongs to the
        caller (RetrievalService)."""
        ...
