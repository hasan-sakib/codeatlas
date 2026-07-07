from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class RetrievalFilters:
    language: str | None = None
    path_prefix: str | None = None
    symbol_kind: str | None = None


@dataclass(frozen=True)
class RetrievalQuery:
    workspace_id: UUID
    query_text: str
    embedding_version: str
    filters: RetrievalFilters = field(default_factory=RetrievalFilters)
    k1: int = 40
    k2: int = 50
    n: int = 10
