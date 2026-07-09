import asyncio
import time
from collections.abc import Awaitable
from typing import Any, TypeVar
from uuid import UUID

import structlog

from app.application.services.fusion import reciprocal_rank_fusion
from app.core.observability.metrics import retrieval_duration_seconds
from app.domain.entities.chunk import Chunk
from app.domain.ports.chunk_repository import ChunkRepository
from app.domain.ports.embedding_port import EmbeddingPort
from app.domain.ports.file_repository import FileRepository
from app.domain.ports.reranker_port import RerankerPort
from app.domain.ports.vector_store_port import VectorStorePort
from app.domain.value_objects.ranked_chunk import RankedChunk
from app.domain.value_objects.retrieval_query import RetrievalQuery

logger = structlog.get_logger(__name__)

T = TypeVar("T")


async def _timed(stage: str, awaitable: Awaitable[T]) -> T:
    start = time.monotonic()
    try:
        return await awaitable
    finally:
        retrieval_duration_seconds.labels(stage=stage).observe(time.monotonic() - start)


class RetrievalService:
    """Framework-agnostic hybrid retrieval: encode -> parallel dense+sparse
    Qdrant search -> Reciprocal Rank Fusion -> Postgres hydration -> rerank.
    Meant to be consumed identically by the future LangGraph agent's
    retrieve_context node and the stateless /search and /ask REST
    endpoints, so retrieval behavior never diverges between the two call
    paths.

    Emits both a structlog `retrieval.completed` event (total wall-clock
    duration) and a per-stage `retrieval_duration_seconds` Prometheus
    histogram (stage=dense|sparse|fuse|rerank) — the log line answers
    "how long did this one request take," the metric answers "which
    stage is slow across many requests."
    """

    def __init__(
        self,
        embedding_port: EmbeddingPort,
        vector_store_port: VectorStorePort,
        chunk_repository: ChunkRepository,
        file_repository: FileRepository,
        reranker_port: RerankerPort,
    ) -> None:
        self._embedding_port = embedding_port
        self._vector_store = vector_store_port
        self._chunk_repository = chunk_repository
        self._file_repository = file_repository
        self._reranker = reranker_port

    async def retrieve(self, query: RetrievalQuery) -> list[RankedChunk]:
        """Full pipeline: encode -> parallel search -> RRF -> hydrate -> rerank -> top-N."""
        start = time.monotonic()
        fused = await self._search_fuse_and_hydrate(query)

        reranked = (
            await _timed("rerank", self._reranker.score(query.query_text, fused)) if fused else []
        )
        result = reranked[: query.n]

        logger.info(
            "retrieval.completed",
            workspace_id=str(query.workspace_id),
            fused_candidates=len(fused),
            returned=len(result),
            duration_seconds=round(time.monotonic() - start, 4),
        )
        return result

    async def retrieve_without_rerank(self, query: RetrievalQuery) -> list[RankedChunk]:
        """Fused+hydrated chunks only, sliced to N directly — for a caller
        applying its own reranking policy instead of this service's."""
        fused = await self._search_fuse_and_hydrate(query)
        return fused[: query.n]

    async def _search_fuse_and_hydrate(self, query: RetrievalQuery) -> list[RankedChunk]:
        embedding = await self._embedding_port.embed_query(query.query_text)
        qdrant_filters = _build_qdrant_filters(query)

        dense_results, sparse_results = await asyncio.gather(
            _timed(
                "dense",
                self._vector_store.search_dense(
                    embedding.dense,
                    workspace_id=query.workspace_id,
                    limit=query.k1,
                    repository_id=query.repository_id,
                    filters=qdrant_filters,
                ),
            ),
            _timed(
                "sparse",
                self._vector_store.search_sparse(
                    embedding.sparse,
                    workspace_id=query.workspace_id,
                    limit=query.k1,
                    repository_id=query.repository_id,
                    filters=qdrant_filters,
                ),
            ),
        )
        dense_ids = [r.chunk_id for r in dense_results]
        sparse_ids = [r.chunk_id for r in sparse_results]
        if not dense_ids and not sparse_ids:
            return []
        return await _timed("fuse", self._fuse_and_hydrate(query, dense_ids, sparse_ids))

    async def _fuse_and_hydrate(
        self, query: RetrievalQuery, dense_ids: list[UUID], sparse_ids: list[UUID]
    ) -> list[RankedChunk]:
        fused = reciprocal_rank_fusion(dense_ids, sparse_ids)[: query.k2]
        fused_ids = [chunk_id for chunk_id, _score in fused]
        scores_by_id = dict(fused)

        chunks = await self._chunk_repository.get_by_ids(fused_ids)
        chunks_by_id: dict[UUID, Chunk] = {chunk.id: chunk for chunk in chunks}

        file_ids = {chunk.file_id for chunk in chunks}
        files = await self._file_repository.get_by_ids(list(file_ids))
        paths_by_file_id = {file.id: file.path for file in files}

        ranked: list[RankedChunk] = []
        for chunk_id in fused_ids:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                continue  # e.g. deleted between indexing and this query

            file_path = paths_by_file_id.get(chunk.file_id, "")
            if query.filters.path_prefix and not file_path.startswith(query.filters.path_prefix):
                # Qdrant's file_path payload field is keyword-indexed for
                # exact match only — prefix filtering happens here,
                # post-hydration, against whatever the fused K2 already
                # contains (not pushed down into the vector search).
                continue

            ranked.append(
                RankedChunk(
                    chunk_id=chunk_id,
                    file_path=file_path,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    symbol_name=chunk.symbol_name,
                    score=scores_by_id[chunk_id],
                    source="fused",
                    text=chunk.content,
                )
            )

        return ranked


def _build_qdrant_filters(query: RetrievalQuery) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "is_active": True,
        "embedding_version": query.embedding_version,
    }
    if query.filters.language is not None:
        filters["language"] = query.filters.language
    if query.filters.symbol_kind is not None:
        filters["symbol_kind"] = query.filters.symbol_kind
    return filters
