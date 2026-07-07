from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.core.constants import QDRANT_DENSE_VECTOR_NAME, QDRANT_SPARSE_VECTOR_NAME
from app.domain.value_objects.chunk_upsert_item import ChunkUpsertItem
from app.domain.value_objects.search_result import SearchResult
from app.infrastructure.vectorstore.collection_schema import alias_name
from app.infrastructure.vectorstore.filters import build_tenant_filter


class QdrantVectorStore:
    """`VectorStorePort` implementation. Every read/write always resolves
    the target collection via the `{prefix}_active` alias, never a
    hardcoded version name, so a version cutover (see collection_schema.py)
    needs no changes here.
    """

    def __init__(self, client: AsyncQdrantClient, *, collection_prefix: str) -> None:
        self._client = client
        self._alias = alias_name(collection_prefix)

    async def upsert(self, items: Sequence[ChunkUpsertItem], *, workspace_id: UUID) -> None:
        if not items:
            return

        mismatched = [item.chunk_id for item in items if item.workspace_id != workspace_id]
        if mismatched:
            raise ValueError(
                f"upsert() called with workspace_id={workspace_id} but chunks {mismatched} "
                "belong to a different workspace"
            )

        points = [_to_point_struct(item) for item in items]
        await self._client.upsert(collection_name=self._alias, points=points)

    async def search_dense(
        self,
        query_vector: list[float],
        *,
        workspace_id: UUID,
        limit: int = 20,
        repository_id: UUID | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[SearchResult]:
        response = await self._client.query_points(
            collection_name=self._alias,
            query=query_vector,
            using=QDRANT_DENSE_VECTOR_NAME,
            query_filter=build_tenant_filter(
                workspace_id, repository_id=repository_id, extra=filters
            ),
            limit=limit,
        )
        return [_to_search_result(point) for point in response.points]

    async def search_sparse(
        self,
        query_sparse: Mapping[int, float],
        *,
        workspace_id: UUID,
        limit: int = 20,
        repository_id: UUID | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[SearchResult]:
        response = await self._client.query_points(
            collection_name=self._alias,
            query=_to_sparse_vector(query_sparse),
            using=QDRANT_SPARSE_VECTOR_NAME,
            query_filter=build_tenant_filter(
                workspace_id, repository_id=repository_id, extra=filters
            ),
            limit=limit,
        )
        return [_to_search_result(point) for point in response.points]

    async def delete_by_filter(
        self,
        *,
        workspace_id: UUID,
        repository_id: UUID | None = None,
        file_id: UUID | None = None,
    ) -> None:
        query_filter = build_tenant_filter(
            workspace_id, repository_id=repository_id, file_id=file_id
        )
        await self._client.delete(
            collection_name=self._alias, points_selector=models.FilterSelector(filter=query_filter)
        )


def _to_point_struct(item: ChunkUpsertItem) -> models.PointStruct:
    return models.PointStruct(
        id=str(item.chunk_id),
        vector={
            QDRANT_DENSE_VECTOR_NAME: item.dense_vector,
            QDRANT_SPARSE_VECTOR_NAME: _to_sparse_vector(item.sparse_vector),
        },
        payload={
            "workspace_id": str(item.workspace_id),
            "repository_id": str(item.repository_id),
            "file_path": item.file_path,
            "language": item.language,
            "symbol_kind": item.symbol_kind,
            "start_line": item.start_line,
            "end_line": item.end_line,
            "embedding_version": item.embedding_version,
            "is_active": item.is_active,
        },
    )


def _to_sparse_vector(sparse: Mapping[int, float]) -> models.SparseVector:
    return models.SparseVector(indices=list(sparse.keys()), values=list(sparse.values()))


def _to_search_result(point: models.ScoredPoint) -> SearchResult:
    return SearchResult(chunk_id=UUID(str(point.id)), score=point.score)
