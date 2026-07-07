from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.services.retrieval_service import RetrievalService
from app.domain.entities.chunk import Chunk, ChunkType, SymbolKind
from app.domain.entities.file import File
from app.domain.value_objects.retrieval_query import RetrievalFilters, RetrievalQuery
from app.domain.value_objects.search_result import SearchResult
from tests.unit.application.services.fakes import (
    FakeChunkRepository,
    FakeEmbeddingPort,
    FakeFileRepository,
    FakeVectorStore,
)


def _make_chunk(chunk_id: UUID, file_id: UUID, **overrides: object) -> Chunk:
    defaults: dict[str, object] = dict(
        id=chunk_id,
        file_id=file_id,
        repository_id=uuid4(),
        symbol_name="foo",
        symbol_kind=SymbolKind.FUNCTION,
        start_line=1,
        end_line=5,
        content="def foo(): pass",
        content_tokens=5,
        chunk_type=ChunkType.CODE,
        imports=[],
        git_blame=None,
        embedding_model="bge-m3",
        embedding_version=1,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return Chunk(**defaults)  # type: ignore[arg-type]


def _make_file(file_id: UUID, path: str) -> File:
    return File(
        id=file_id,
        repository_id=uuid4(),
        path=path,
        language="python",
        size_bytes=100,
        content_hash="abc",
        last_commit_sha=None,
        last_modified_at=None,
        is_deleted=False,
        indexed_at=None,
    )


async def test_retrieve_calls_dense_and_sparse_with_workspace_and_pushed_down_filters() -> None:
    file_id, chunk_id, workspace_id = uuid4(), uuid4(), uuid4()
    embedding_port = FakeEmbeddingPort()
    vector_store = FakeVectorStore(dense_results=[SearchResult(chunk_id, 0.9)])
    chunk_repo = FakeChunkRepository([_make_chunk(chunk_id, file_id)])
    file_repo = FakeFileRepository([_make_file(file_id, "app.py")])
    service = RetrievalService(embedding_port, vector_store, chunk_repo, file_repo)

    query = RetrievalQuery(
        workspace_id=workspace_id,
        query_text="find foo",
        embedding_version="bge-m3:v1",
        filters=RetrievalFilters(language="python", symbol_kind="function"),
        k1=10,
        k2=10,
        n=5,
    )

    results = await service.retrieve(query)

    assert embedding_port.queries == ["find foo"]
    assert len(vector_store.dense_calls) == 1
    call = vector_store.dense_calls[0]
    assert call["workspace_id"] == workspace_id
    assert call["limit"] == 10
    assert call["filters"] == {
        "is_active": True,
        "embedding_version": "bge-m3:v1",
        "language": "python",
        "symbol_kind": "function",
    }
    assert vector_store.sparse_calls[0]["filters"] == call["filters"]
    assert len(results) == 1
    assert results[0].chunk_id == chunk_id
    assert results[0].file_path == "app.py"
    assert results[0].source == "fused"
    assert results[0].text == "def foo(): pass"


async def test_retrieve_preserves_fused_order_regardless_of_postgres_return_order() -> None:
    file_id = uuid4()
    a, b, c = uuid4(), uuid4(), uuid4()
    vector_store = FakeVectorStore(
        dense_results=[SearchResult(a, 0.9), SearchResult(b, 0.8), SearchResult(c, 0.7)]
    )
    chunk_repo = FakeChunkRepository(
        [_make_chunk(a, file_id), _make_chunk(b, file_id), _make_chunk(c, file_id)]
    )
    file_repo = FakeFileRepository([_make_file(file_id, "app.py")])
    service = RetrievalService(FakeEmbeddingPort(), vector_store, chunk_repo, file_repo)

    query = RetrievalQuery(workspace_id=uuid4(), query_text="q", embedding_version="v1")
    results = await service.retrieve(query)

    assert [r.chunk_id for r in results] == [a, b, c]
    assert chunk_repo.requested_ids == [a, b, c]  # fake really did scramble the return order


async def test_zero_hits_returns_empty_list_without_calling_repositories() -> None:
    vector_store = FakeVectorStore(dense_results=[], sparse_results=[])
    chunk_repo = FakeChunkRepository([])
    service = RetrievalService(
        FakeEmbeddingPort(), vector_store, chunk_repo, FakeFileRepository([])
    )

    results = await service.retrieve(
        RetrievalQuery(workspace_id=uuid4(), query_text="q", embedding_version="v1")
    )

    assert results == []
    assert chunk_repo.call_count == 0


async def test_path_prefix_filters_post_hydration() -> None:
    file_a, file_b = uuid4(), uuid4()
    chunk_a, chunk_b = uuid4(), uuid4()
    vector_store = FakeVectorStore(
        dense_results=[SearchResult(chunk_a, 0.9), SearchResult(chunk_b, 0.8)]
    )
    chunk_repo = FakeChunkRepository([_make_chunk(chunk_a, file_a), _make_chunk(chunk_b, file_b)])
    file_repo = FakeFileRepository(
        [_make_file(file_a, "src/app.py"), _make_file(file_b, "tests/test_app.py")]
    )
    service = RetrievalService(FakeEmbeddingPort(), vector_store, chunk_repo, file_repo)

    query = RetrievalQuery(
        workspace_id=uuid4(),
        query_text="q",
        embedding_version="v1",
        filters=RetrievalFilters(path_prefix="src/"),
    )
    results = await service.retrieve(query)

    assert [r.chunk_id for r in results] == [chunk_a]


async def test_result_sliced_to_n() -> None:
    file_id = uuid4()
    ids = [uuid4() for _ in range(5)]
    vector_store = FakeVectorStore(
        dense_results=[SearchResult(cid, 1.0 - i * 0.1) for i, cid in enumerate(ids)]
    )
    chunk_repo = FakeChunkRepository([_make_chunk(cid, file_id) for cid in ids])
    file_repo = FakeFileRepository([_make_file(file_id, "app.py")])
    service = RetrievalService(FakeEmbeddingPort(), vector_store, chunk_repo, file_repo)

    query = RetrievalQuery(workspace_id=uuid4(), query_text="q", embedding_version="v1", n=2)
    results = await service.retrieve(query)

    assert [r.chunk_id for r in results] == ids[:2]
