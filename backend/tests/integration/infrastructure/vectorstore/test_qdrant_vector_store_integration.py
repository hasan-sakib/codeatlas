from uuid import uuid4

import pytest
import pytest_asyncio
from qdrant_client import AsyncQdrantClient

from app.domain.value_objects.chunk_upsert_item import ChunkUpsertItem
from app.infrastructure.vectorstore.collection_schema import (
    alias_name,
    create_versioned_collection,
    list_collection_versions,
    point_alias_to,
)
from app.infrastructure.vectorstore.qdrant_vector_store import QdrantVectorStore

pytestmark = pytest.mark.integration


def _make_item(workspace_id, repository_id, **overrides: object) -> ChunkUpsertItem:
    defaults: dict[str, object] = dict(
        chunk_id=uuid4(),
        dense_vector=[0.1, 0.2, 0.3, 0.4],
        sparse_vector={1: 0.5, 2: 0.3},
        workspace_id=workspace_id,
        repository_id=repository_id,
        file_path="a.py",
        language="python",
        symbol_kind="function",
        start_line=1,
        end_line=5,
        embedding_version="v1",
    )
    defaults.update(overrides)
    return ChunkUpsertItem(**defaults)  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def qdrant_setup(qdrant_container):
    client: AsyncQdrantClient = qdrant_container.get_async_client()
    # Unique prefix per test — the container is module-scoped, so each
    # test gets its own isolated collection/alias rather than sharing
    # state across tests.
    prefix = f"test_{uuid4().hex[:8]}"
    collection = await create_versioned_collection(
        client, prefix=prefix, version=1, embedding_dim=4
    )
    await point_alias_to(client, alias_name(prefix), collection)
    store = QdrantVectorStore(client, collection_prefix=prefix)
    return store, client, prefix


async def test_upsert_and_search_dense_round_trip(qdrant_setup) -> None:
    store, _client, _prefix = qdrant_setup
    workspace_id, repository_id = uuid4(), uuid4()
    item = _make_item(workspace_id, repository_id)

    await store.upsert([item], workspace_id=workspace_id)
    results = await store.search_dense(item.dense_vector, workspace_id=workspace_id)

    assert len(results) == 1
    assert results[0].chunk_id == item.chunk_id


async def test_upsert_and_search_sparse_round_trip(qdrant_setup) -> None:
    store, _client, _prefix = qdrant_setup
    workspace_id, repository_id = uuid4(), uuid4()
    item = _make_item(workspace_id, repository_id)

    await store.upsert([item], workspace_id=workspace_id)
    results = await store.search_sparse(item.sparse_vector, workspace_id=workspace_id)

    assert len(results) == 1
    assert results[0].chunk_id == item.chunk_id


async def test_search_never_returns_another_workspaces_point(qdrant_setup) -> None:
    """The core multi-tenancy regression: two workspaces upsert points
    with the same-shaped payload/vector; a search scoped to workspace A
    must never return workspace B's point, even against an identical
    query vector."""
    store, _client, _prefix = qdrant_setup
    workspace_a, workspace_b = uuid4(), uuid4()
    repository_id = uuid4()  # deliberately the same "shape" for both
    item_a = _make_item(workspace_a, repository_id)
    item_b = _make_item(workspace_b, repository_id, dense_vector=item_a.dense_vector)

    await store.upsert([item_a], workspace_id=workspace_a)
    await store.upsert([item_b], workspace_id=workspace_b)

    results_a = await store.search_dense(item_a.dense_vector, workspace_id=workspace_a)
    results_b = await store.search_dense(item_a.dense_vector, workspace_id=workspace_b)

    assert {r.chunk_id for r in results_a} == {item_a.chunk_id}
    assert {r.chunk_id for r in results_b} == {item_b.chunk_id}


async def test_delete_by_filter_removes_only_the_matching_scope(qdrant_setup) -> None:
    store, _client, _prefix = qdrant_setup
    workspace_id = uuid4()
    repo_to_delete, repo_to_keep = uuid4(), uuid4()
    item_delete = _make_item(workspace_id, repo_to_delete)
    item_keep = _make_item(workspace_id, repo_to_keep, dense_vector=[0.9, 0.8, 0.7, 0.6])

    await store.upsert([item_delete, item_keep], workspace_id=workspace_id)
    await store.delete_by_filter(workspace_id=workspace_id, repository_id=repo_to_delete)

    remaining = await store.search_dense(
        item_keep.dense_vector, workspace_id=workspace_id, limit=10
    )
    assert {r.chunk_id for r in remaining} == {item_keep.chunk_id}


async def test_alias_cutover_points_search_at_the_new_collection(qdrant_setup) -> None:
    store, client, prefix = qdrant_setup
    workspace_id, repository_id = uuid4(), uuid4()
    item = _make_item(workspace_id, repository_id)
    await store.upsert([item], workspace_id=workspace_id)

    # Cut over to a brand-new v2 collection — the old point was never
    # copied into it, so a search against the (now-repointed) alias
    # returns nothing, demonstrating the alias genuinely moved.
    await create_versioned_collection(client, prefix=prefix, version=2, embedding_dim=4)
    await point_alias_to(client, alias_name(prefix), f"{prefix}_v2")

    results_after_cutover = await store.search_dense(item.dense_vector, workspace_id=workspace_id)
    assert results_after_cutover == []

    versions = await list_collection_versions(client, prefix)
    assert versions == [f"{prefix}_v1", f"{prefix}_v2"]
