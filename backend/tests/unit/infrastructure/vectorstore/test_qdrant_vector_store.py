from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from qdrant_client import models

from app.domain.value_objects.chunk_upsert_item import ChunkUpsertItem
from app.domain.value_objects.search_result import SearchResult
from app.infrastructure.vectorstore.qdrant_vector_store import QdrantVectorStore


def _make_item(workspace_id: UUID, **overrides: object) -> ChunkUpsertItem:
    defaults: dict[str, object] = dict(
        chunk_id=uuid4(),
        dense_vector=[0.1, 0.2],
        sparse_vector={1: 0.5},
        workspace_id=workspace_id,
        repository_id=uuid4(),
        file_path="a.py",
        language="python",
        symbol_kind="function",
        start_line=1,
        end_line=2,
        embedding_version="v1",
    )
    defaults.update(overrides)
    return ChunkUpsertItem(**defaults)  # type: ignore[arg-type]


def _scored_point(chunk_id: UUID, score: float) -> models.ScoredPoint:
    return models.ScoredPoint(id=str(chunk_id), version=1, score=score, payload={})


async def test_upsert_builds_point_struct_with_str_id_and_full_payload() -> None:
    client = AsyncMock()
    store = QdrantVectorStore(client, collection_prefix="code_chunks")
    workspace_id = uuid4()
    item = _make_item(workspace_id)

    await store.upsert([item], workspace_id=workspace_id)

    client.upsert.assert_awaited_once()
    kwargs = client.upsert.call_args.kwargs
    assert kwargs["collection_name"] == "code_chunks_active"
    (point,) = kwargs["points"]
    assert point.id == str(item.chunk_id)
    assert point.payload["workspace_id"] == str(item.workspace_id)
    assert point.payload["repository_id"] == str(item.repository_id)
    assert point.payload["file_path"] == "a.py"
    assert point.payload["is_active"] is True
    assert point.payload["embedding_version"] == "v1"


async def test_upsert_raises_on_workspace_mismatch_and_never_calls_client() -> None:
    client = AsyncMock()
    store = QdrantVectorStore(client, collection_prefix="code_chunks")
    item = _make_item(uuid4())

    with pytest.raises(ValueError, match="different workspace"):
        await store.upsert([item], workspace_id=uuid4())

    client.upsert.assert_not_awaited()


async def test_upsert_with_no_items_is_a_noop() -> None:
    client = AsyncMock()
    store = QdrantVectorStore(client, collection_prefix="code_chunks")

    await store.upsert([], workspace_id=uuid4())

    client.upsert.assert_not_awaited()


async def test_search_dense_scopes_query_to_workspace_and_maps_results() -> None:
    client = AsyncMock()
    chunk_id = uuid4()
    client.query_points.return_value = MagicMock(points=[_scored_point(chunk_id, 0.9)])
    store = QdrantVectorStore(client, collection_prefix="code_chunks")
    workspace_id = uuid4()

    results = await store.search_dense([0.1, 0.2], workspace_id=workspace_id, limit=5)

    client.query_points.assert_awaited_once()
    kwargs = client.query_points.call_args.kwargs
    assert kwargs["collection_name"] == "code_chunks_active"
    assert kwargs["using"] == "dense"
    assert kwargs["limit"] == 5
    query_filter = kwargs["query_filter"]
    assert query_filter.must is not None
    assert any(
        c.key == "workspace_id" and c.match.value == str(workspace_id) for c in query_filter.must
    )
    assert results == [SearchResult(chunk_id=chunk_id, score=0.9)]


async def test_search_dense_with_repository_id_and_extra_filters() -> None:
    client = AsyncMock()
    client.query_points.return_value = MagicMock(points=[])
    store = QdrantVectorStore(client, collection_prefix="code_chunks")
    workspace_id, repository_id = uuid4(), uuid4()

    await store.search_dense(
        [0.1, 0.2],
        workspace_id=workspace_id,
        repository_id=repository_id,
        filters={"language": "python"},
    )

    query_filter = client.query_points.call_args.kwargs["query_filter"]
    assert query_filter.must is not None
    keys = {c.key for c in query_filter.must}
    assert keys == {"workspace_id", "repository_id", "language"}


async def test_search_sparse_uses_sparse_named_vector() -> None:
    client = AsyncMock()
    chunk_id = uuid4()
    client.query_points.return_value = MagicMock(points=[_scored_point(chunk_id, 0.5)])
    store = QdrantVectorStore(client, collection_prefix="code_chunks")
    workspace_id = uuid4()

    results = await store.search_sparse({1: 0.5, 2: 0.3}, workspace_id=workspace_id)

    kwargs = client.query_points.call_args.kwargs
    assert kwargs["using"] == "sparse"
    assert isinstance(kwargs["query"], models.SparseVector)
    assert kwargs["query"].indices == [1, 2]
    assert kwargs["query"].values == [0.5, 0.3]
    assert results == [SearchResult(chunk_id=chunk_id, score=0.5)]


async def test_delete_by_filter_scopes_to_workspace_and_optional_ids() -> None:
    client = AsyncMock()
    store = QdrantVectorStore(client, collection_prefix="code_chunks")
    workspace_id, repository_id, file_id = uuid4(), uuid4(), uuid4()

    await store.delete_by_filter(
        workspace_id=workspace_id, repository_id=repository_id, file_id=file_id
    )

    client.delete.assert_awaited_once()
    kwargs = client.delete.call_args.kwargs
    assert kwargs["collection_name"] == "code_chunks_active"
    selector = kwargs["points_selector"]
    assert isinstance(selector, models.FilterSelector)
    keys = {c.key for c in selector.filter.must}
    assert keys == {"workspace_id", "repository_id", "file_id"}
