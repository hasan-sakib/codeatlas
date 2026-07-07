from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ChunkUpsertItem:
    """Deliberately excludes chunk text — Qdrant payload stays lean
    (filterable/displayable metadata only); the text of record lives in
    Postgres (`chunks.content`, Module 4)."""

    chunk_id: UUID  # == Postgres chunks.id, used verbatim as the Qdrant point id
    dense_vector: list[float]
    sparse_vector: dict[int, float]
    workspace_id: UUID
    repository_id: UUID
    file_path: str
    language: str
    symbol_kind: str
    start_line: int
    end_line: int
    embedding_version: str
    is_active: bool = True
