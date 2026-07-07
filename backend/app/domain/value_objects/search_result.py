from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SearchResult:
    chunk_id: UUID
    score: float
