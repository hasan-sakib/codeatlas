from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any
from uuid import UUID

from app.domain.entities.chunk import Chunk
from app.domain.entities.file import File
from app.domain.value_objects.chunk_upsert_item import ChunkUpsertItem
from app.domain.value_objects.embedding_result import EmbeddingResult
from app.domain.value_objects.ranked_chunk import RankedChunk
from app.domain.value_objects.search_result import SearchResult


class FakeEmbeddingPort:
    def __init__(
        self, dense: list[float] | None = None, sparse: dict[int, float] | None = None
    ) -> None:
        self.dense = dense if dense is not None else [0.1, 0.2]
        self.sparse = sparse if sparse is not None else {1: 0.5}
        self.queries: list[str] = []

    async def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingResult]:
        raise NotImplementedError

    async def embed_query(self, text: str) -> EmbeddingResult:
        self.queries.append(text)
        return EmbeddingResult(dense=self.dense, sparse=self.sparse, model_id="fake:v1")

    async def warm_up(self) -> None:
        pass


class FakeVectorStore:
    def __init__(
        self,
        dense_results: list[SearchResult] | None = None,
        sparse_results: list[SearchResult] | None = None,
    ) -> None:
        self.dense_results = dense_results or []
        self.sparse_results = sparse_results or []
        self.dense_calls: list[dict[str, Any]] = []
        self.sparse_calls: list[dict[str, Any]] = []

    async def upsert(self, items: Sequence[ChunkUpsertItem], *, workspace_id: UUID) -> None:
        raise NotImplementedError

    async def search_dense(
        self,
        query_vector: list[float],
        *,
        workspace_id: UUID,
        limit: int = 20,
        repository_id: UUID | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[SearchResult]:
        self.dense_calls.append(
            dict(
                query_vector=query_vector,
                workspace_id=workspace_id,
                limit=limit,
                repository_id=repository_id,
                filters=filters,
            )
        )
        return self.dense_results

    async def search_sparse(
        self,
        query_sparse: Mapping[int, float],
        *,
        workspace_id: UUID,
        limit: int = 20,
        repository_id: UUID | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[SearchResult]:
        self.sparse_calls.append(
            dict(
                query_sparse=query_sparse,
                workspace_id=workspace_id,
                limit=limit,
                repository_id=repository_id,
                filters=filters,
            )
        )
        return self.sparse_results

    async def delete_by_filter(
        self,
        *,
        workspace_id: UUID,
        repository_id: UUID | None = None,
        file_id: UUID | None = None,
    ) -> None:
        raise NotImplementedError


class FakeChunkRepository:
    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = {chunk.id: chunk for chunk in chunks}
        self.requested_ids: list[UUID] = []
        self.call_count = 0

    async def add_many(self, chunks: Sequence[Chunk]) -> None:
        raise NotImplementedError

    async def get_by_id(self, chunk_id: UUID) -> Chunk | None:
        raise NotImplementedError

    async def get_by_ids(self, chunk_ids: Sequence[UUID]) -> list[Chunk]:
        self.call_count += 1
        self.requested_ids = list(chunk_ids)
        # Deliberately returned in REVERSE order of the request, to prove
        # the service re-sorts by fused rank rather than trusting
        # whatever order Postgres happens to return.
        return [self._chunks[cid] for cid in reversed(chunk_ids) if cid in self._chunks]

    async def list_by_file(self, file_id: UUID) -> list[Chunk]:
        raise NotImplementedError

    async def deactivate_by_file(self, file_id: UUID) -> None:
        raise NotImplementedError

    async def delete_by_file(self, file_id: UUID) -> None:
        raise NotImplementedError

    async def delete_by_repository(self, repository_id: UUID) -> None:
        raise NotImplementedError


class FakeFileRepository:
    def __init__(self, files: list[File]) -> None:
        self._files = {file.id: file for file in files}

    async def add(self, file: File) -> File:
        raise NotImplementedError

    async def get_by_id(self, file_id: UUID) -> File | None:
        raise NotImplementedError

    async def get_by_ids(self, file_ids: Sequence[UUID]) -> list[File]:
        return [self._files[fid] for fid in file_ids if fid in self._files]

    async def get_by_repository_and_path(self, repository_id: UUID, path: str) -> File | None:
        raise NotImplementedError

    async def list_by_repository(self, repository_id: UUID) -> list[File]:
        raise NotImplementedError

    async def upsert(self, file: File) -> File:
        raise NotImplementedError


class FakeReranker:
    """Identity by default — returns the input order unchanged, just
    retags source="reranked" — good enough for tests that only care that
    RetrievalService wires the reranker in correctly, not about
    reranking's own scoring behavior (that's Module 12's own test suite).
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[RankedChunk]]] = []

    async def score(self, query: str, chunks: list[RankedChunk]) -> list[RankedChunk]:
        self.calls.append((query, list(chunks)))
        return [replace(chunk, source="reranked") for chunk in chunks]
