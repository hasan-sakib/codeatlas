from datetime import UTC, datetime
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient

from app.application.services.retrieval_service import RetrievalService
from app.domain.entities.chunk import Chunk, ChunkType, SymbolKind
from app.domain.entities.file import File
from app.domain.entities.repository import Repository, RepositorySourceType, RepositoryStatus
from app.domain.entities.user import User
from app.domain.entities.workspace import Workspace
from app.domain.value_objects.chunk_upsert_item import ChunkUpsertItem
from app.domain.value_objects.embedding_result import EmbeddingResult
from app.domain.value_objects.retrieval_query import RetrievalQuery
from app.infrastructure.db.repositories.sqlalchemy_chunk_repository import (
    SqlAlchemyChunkRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_file_repository import SqlAlchemyFileRepository
from app.infrastructure.db.repositories.sqlalchemy_repository_repository import (
    SqlAlchemyRepositoryRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.infrastructure.db.repositories.sqlalchemy_workspace_repository import (
    SqlAlchemyWorkspaceRepository,
)
from app.infrastructure.vectorstore.collection_schema import (
    alias_name,
    create_versioned_collection,
    point_alias_to,
)
from app.infrastructure.vectorstore.qdrant_vector_store import QdrantVectorStore

pytestmark = pytest.mark.integration


class _StubEmbeddingPort:
    """Real BGE-M3 inference isn't used here (see Module 9's docs on
    keeping the checked-in suite model-free) — this returns a
    hand-crafted query vector so dense-search relevance is deterministic
    and independently verifiable, while Qdrant and Postgres are both
    real.
    """

    def __init__(self, dense: list[float], sparse: dict[int, float]) -> None:
        self._dense = dense
        self._sparse = sparse

    async def embed_batch(self, texts: object) -> list[EmbeddingResult]:
        raise NotImplementedError

    async def embed_query(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(dense=self._dense, sparse=self._sparse, model_id="stub:v1")


async def _seed_postgres_chain(db_session) -> tuple[Repository, list[File]]:
    now = datetime.now(UTC)
    user = User(
        id=uuid4(),
        email="amina@example.com",
        hashed_password="irrelevant",
        full_name=None,
        is_active=True,
        is_verified=True,
        created_at=now,
        updated_at=now,
    )
    await SqlAlchemyUserRepository(db_session).add(user)

    workspace = Workspace(
        id=uuid4(),
        owner_id=user.id,
        name="Test Workspace",
        slug="test-workspace",
        description=None,
        created_at=now,
        updated_at=now,
    )
    await SqlAlchemyWorkspaceRepository(db_session).add(workspace)

    repository = Repository(
        id=uuid4(),
        workspace_id=workspace.id,
        source_type=RepositorySourceType.GIT_URL,
        git_url="https://github.com/example/repo.git",
        default_branch="main",
        local_path=None,
        last_indexed_commit_sha=None,
        status=RepositoryStatus.READY,
        created_at=now,
        updated_at=now,
    )
    await SqlAlchemyRepositoryRepository(db_session).add(repository)

    file_repo = SqlAlchemyFileRepository(db_session)
    files = []
    for path in ("src/app.py", "src/util.py", "src/other.py"):
        file = File(
            id=uuid4(),
            repository_id=repository.id,
            path=path,
            language="python",
            size_bytes=100,
            content_hash=f"hash-{path}",
            last_commit_sha=None,
            last_modified_at=None,
            is_deleted=False,
            indexed_at=None,
        )
        await file_repo.add(file)
        files.append(file)

    await db_session.commit()
    return repository, files


async def test_retrieve_end_to_end_ranks_the_closest_seeded_vector_first(
    db_session, qdrant_container
) -> None:
    repository, files = await _seed_postgres_chain(db_session)
    repository_id, workspace_id = repository.id, repository.workspace_id

    chunk_repo = SqlAlchemyChunkRepository(db_session)
    chunks = [
        Chunk(
            id=uuid4(),
            file_id=files[i].id,
            repository_id=repository_id,
            symbol_name=f"symbol_{i}",
            symbol_kind=SymbolKind.FUNCTION,
            start_line=1,
            end_line=5,
            content=f"def symbol_{i}(): pass",
            content_tokens=5,
            chunk_type=ChunkType.CODE,
            imports=[],
            git_blame=None,
            embedding_model="bge-m3",
            embedding_version=1,
            is_active=True,
        )
        for i in range(3)
    ]
    await chunk_repo.add_many(chunks)
    await db_session.commit()

    client: AsyncQdrantClient = qdrant_container.get_async_client()
    prefix = f"test_{uuid4().hex[:8]}"
    collection = await create_versioned_collection(
        client, prefix=prefix, version=1, embedding_dim=4
    )
    await point_alias_to(client, alias_name(prefix), collection)
    vector_store = QdrantVectorStore(client, collection_prefix=prefix)

    # Chunk 0's vector is the query vector itself (closest); 1 and 2 are
    # deliberately dissimilar, so dense search must rank chunk 0 first.
    query_vector = [1.0, 0.0, 0.0, 0.0]
    vectors = {
        chunks[0].id: [1.0, 0.0, 0.0, 0.0],
        chunks[1].id: [0.0, 1.0, 0.0, 0.0],
        chunks[2].id: [0.0, 0.0, 1.0, 0.0],
    }
    items = [
        ChunkUpsertItem(
            chunk_id=chunk.id,
            dense_vector=vectors[chunk.id],
            sparse_vector={},
            workspace_id=workspace_id,
            repository_id=repository_id,
            file_path=files[i].path,
            language="python",
            symbol_kind="function",
            start_line=1,
            end_line=5,
            embedding_version="v1",
        )
        for i, chunk in enumerate(chunks)
    ]
    await vector_store.upsert(items, workspace_id=workspace_id)

    embedding_port = _StubEmbeddingPort(dense=query_vector, sparse={})
    file_repo = SqlAlchemyFileRepository(db_session)
    service = RetrievalService(embedding_port, vector_store, chunk_repo, file_repo)

    query = RetrievalQuery(workspace_id=workspace_id, query_text="anything", embedding_version="v1")
    results = await service.retrieve(query)

    assert results[0].chunk_id == chunks[0].id
    assert results[0].file_path == "src/app.py"
    assert results[0].text == "def symbol_0(): pass"
    assert results[0].source == "fused"
