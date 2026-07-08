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
    # Optional — VectorStorePort.search_dense/search_sparse have always
    # accepted this (Module 10), but RetrievalQuery never exposed it,
    # leaving path_prefix as the only way to scope a query, which can't
    # safely disambiguate two repositories in the same workspace sharing
    # a relative path (e.g. both have "src/main.py"). Added here (Module
    # 17) since GenerateDocumentationUseCase's repository-scoped
    # generation needs a real repository-level filter, not a path guess.
    repository_id: UUID | None = None
    filters: RetrievalFilters = field(default_factory=RetrievalFilters)
    k1: int = 40
    k2: int = 50
    n: int = 10
