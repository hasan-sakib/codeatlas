from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from uuid import UUID

from app.domain.value_objects.chunk_upsert_item import ChunkUpsertItem
from app.domain.value_objects.search_result import SearchResult


class VectorStorePort(Protocol):
    """Every method requires `workspace_id` as a mandatory keyword-only
    parameter — no method on this port has a code path that omits it, so
    it's structurally impossible for a caller to issue an unscoped query.
    """

    async def upsert(self, items: Sequence[ChunkUpsertItem], *, workspace_id: UUID) -> None: ...

    async def search_dense(
        self,
        query_vector: list[float],
        *,
        workspace_id: UUID,
        limit: int = 20,
        repository_id: UUID | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[SearchResult]: ...

    async def search_sparse(
        self,
        query_sparse: Mapping[int, float],
        *,
        workspace_id: UUID,
        limit: int = 20,
        repository_id: UUID | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[SearchResult]: ...

    async def delete_by_filter(
        self,
        *,
        workspace_id: UUID,
        repository_id: UUID | None = None,
        file_id: UUID | None = None,
    ) -> None: ...
