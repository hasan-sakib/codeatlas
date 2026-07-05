from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.entities.chunk import Chunk, ChunkType, SymbolKind
from app.domain.entities.file import File
from app.domain.entities.repository import Repository, RepositorySourceType, RepositoryStatus
from app.domain.entities.user import User
from app.domain.entities.workspace import Workspace
from app.infrastructure.db.repositories.sqlalchemy_chunk_repository import (
    SqlAlchemyChunkRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_file_repository import (
    SqlAlchemyFileRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_repository_repository import (
    SqlAlchemyRepositoryRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_workspace_repository import (
    SqlAlchemyWorkspaceRepository,
)

pytestmark = pytest.mark.integration

_PLACEHOLDER_TS = datetime.now(UTC)  # overwritten by server_default on insert


async def _seed_user(session) -> User:
    return await SqlAlchemyUserRepository(session).add(
        User(
            id=uuid4(),
            email=f"{uuid4()}@example.com",
            hashed_password="hashed",
            full_name=None,
            is_active=True,
            is_verified=False,
            created_at=_PLACEHOLDER_TS,
            updated_at=_PLACEHOLDER_TS,
        )
    )


async def _seed_workspace(session, owner_id) -> Workspace:
    return await SqlAlchemyWorkspaceRepository(session).add(
        Workspace(
            id=uuid4(),
            owner_id=owner_id,
            name="Test Workspace",
            slug=f"test-{uuid4().hex[:8]}",
            description=None,
            created_at=_PLACEHOLDER_TS,
            updated_at=_PLACEHOLDER_TS,
        )
    )


async def _seed_repository(session, workspace_id) -> Repository:
    return await SqlAlchemyRepositoryRepository(session).add(
        Repository(
            id=uuid4(),
            workspace_id=workspace_id,
            source_type=RepositorySourceType.GIT_URL,
            git_url="https://github.com/example/repo.git",
            default_branch="main",
            local_path=None,
            last_indexed_commit_sha=None,
            status=RepositoryStatus.PENDING,
            created_at=_PLACEHOLDER_TS,
            updated_at=_PLACEHOLDER_TS,
        )
    )


async def _seed_file(session, repository_id, path: str = "src/main.py") -> File:
    return await SqlAlchemyFileRepository(session).add(
        File(
            id=uuid4(),
            repository_id=repository_id,
            path=path,
            language="python",
            size_bytes=100,
            content_hash="a" * 64,
            last_commit_sha=None,
            last_modified_at=None,
            is_deleted=False,
            indexed_at=None,
        )
    )


async def test_full_aggregate_chain_persists_and_reads_back(db_session) -> None:
    user = await _seed_user(db_session)
    workspace = await _seed_workspace(db_session, user.id)
    repository = await _seed_repository(db_session, workspace.id)
    file = await _seed_file(db_session, repository.id)

    assert user.created_at is not None
    assert workspace.owner_id == user.id
    assert repository.workspace_id == workspace.id
    assert file.repository_id == repository.id


async def test_unique_constraint_rejects_duplicate_repository_and_path(db_session) -> None:
    user = await _seed_user(db_session)
    workspace = await _seed_workspace(db_session, user.id)
    repository = await _seed_repository(db_session, workspace.id)
    await _seed_file(db_session, repository.id, path="src/duplicate.py")

    with pytest.raises(IntegrityError):
        await _seed_file(db_session, repository.id, path="src/duplicate.py")


async def test_fk_cascade_deleting_repository_removes_files_and_chunks(db_session) -> None:
    user = await _seed_user(db_session)
    workspace = await _seed_workspace(db_session, user.id)
    repository = await _seed_repository(db_session, workspace.id)
    file = await _seed_file(db_session, repository.id)

    chunk_repo = SqlAlchemyChunkRepository(db_session)
    await chunk_repo.add_many(
        [
            Chunk(
                id=uuid4(),
                file_id=file.id,
                repository_id=repository.id,
                symbol_name="foo",
                symbol_kind=SymbolKind.FUNCTION,
                start_line=1,
                end_line=5,
                content="def foo(): pass",
                content_tokens=4,
                chunk_type=ChunkType.CODE,
            )
        ]
    )

    file_repo = SqlAlchemyFileRepository(db_session)
    repo_repo = SqlAlchemyRepositoryRepository(db_session)

    await repo_repo.delete(repository.id)
    await db_session.flush()

    assert await file_repo.get_by_id(file.id) is None
    assert await chunk_repo.list_by_file(file.id) == []


async def test_chunk_round_trip_preserves_metadata_fields(db_session) -> None:
    user = await _seed_user(db_session)
    workspace = await _seed_workspace(db_session, user.id)
    repository = await _seed_repository(db_session, workspace.id)
    file = await _seed_file(db_session, repository.id)

    chunk_repo = SqlAlchemyChunkRepository(db_session)
    chunk_id = uuid4()
    await chunk_repo.add_many(
        [
            Chunk(
                id=chunk_id,
                file_id=file.id,
                repository_id=repository.id,
                symbol_name="PaymentService",
                symbol_kind=SymbolKind.CLASS,
                start_line=10,
                end_line=42,
                content="class PaymentService: ...",
                content_tokens=12,
                chunk_type=ChunkType.CODE,
                imports=["os", "typing"],
                git_blame={"author": "alice", "commit_sha": "abc123"},
                embedding_model="bge-m3:v1",
                embedding_version=1,
            )
        ]
    )

    fetched = await chunk_repo.get_by_id(chunk_id)

    assert fetched is not None
    assert fetched.symbol_name == "PaymentService"
    assert fetched.symbol_kind == SymbolKind.CLASS
    assert fetched.start_line == 10
    assert fetched.end_line == 42
    assert fetched.imports == ["os", "typing"]
    assert fetched.git_blame == {"author": "alice", "commit_sha": "abc123"}
    assert fetched.embedding_version == 1
