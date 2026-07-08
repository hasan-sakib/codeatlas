from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.agent.tools.get_git_blame_tool import GetGitBlameTool
from app.domain.entities.chunk import Chunk, ChunkType, SymbolKind
from app.domain.entities.file import File
from app.domain.entities.repository import Repository, RepositorySourceType, RepositoryStatus
from app.domain.value_objects.clone_result import BlameEntry


class FakeChunkRepository:
    def __init__(self, chunk: Chunk) -> None:
        self._chunk = chunk

    async def get_by_id(self, chunk_id):
        return self._chunk if chunk_id == self._chunk.id else None


class FakeFileRepository:
    def __init__(self, file: File) -> None:
        self._file = file

    async def get_by_id(self, file_id):
        return self._file if file_id == self._file.id else None


class FakeRepositoryRepository:
    def __init__(self, repository: Repository | None) -> None:
        self._repository = repository

    async def get_by_id(self, repository_id):
        return self._repository


class FakeGitPort:
    def __init__(self, entries: list[BlameEntry]) -> None:
        self.entries = entries
        self.calls: list[tuple] = []

    async def clone(self, url, dest_dir, *, shallow=True):
        raise NotImplementedError

    async def get_blame(self, repo_path, file_path, start_line, end_line):
        self.calls.append((repo_path, file_path, start_line, end_line))
        return self.entries


def _chunk(file_id, repository_id) -> Chunk:
    return Chunk(
        id=uuid4(),
        file_id=file_id,
        repository_id=repository_id,
        symbol_name="foo",
        symbol_kind=SymbolKind.FUNCTION,
        start_line=1,
        end_line=5,
        content="def foo(): pass",
        content_tokens=5,
        chunk_type=ChunkType.CODE,
    )


def _file(repository_id, path="app/foo.py") -> File:
    return File(
        id=uuid4(),
        repository_id=repository_id,
        path=path,
        language="python",
        size_bytes=10,
        content_hash="abc",
        last_commit_sha=None,
        last_modified_at=None,
        is_deleted=False,
        indexed_at=None,
    )


def _repository(local_path: str | None) -> Repository:
    now = datetime.now(UTC)
    return Repository(
        id=uuid4(),
        workspace_id=uuid4(),
        source_type=RepositorySourceType.GIT_URL,
        git_url="https://github.com/example/repo.git",
        default_branch="main",
        local_path=local_path,
        last_indexed_commit_sha=None,
        status=RepositoryStatus.READY,
        created_at=now,
        updated_at=now,
    )


async def test_get_git_blame_tool_returns_formatted_entries() -> None:
    repository = _repository(local_path="/tmp/clone")
    file = _file(repository.id)
    chunk = _chunk(file.id, repository.id)
    entries = [
        BlameEntry(author="Jane Doe", commit_sha="abcdef1234567890", committed_at=datetime.now(UTC))
    ]
    git_port = FakeGitPort(entries)

    tool = GetGitBlameTool(
        FakeChunkRepository(chunk),
        FakeFileRepository(file),
        FakeRepositoryRepository(repository),
        git_port,
    )
    result = await tool(chunk.id)

    assert "app/foo.py:1-5" in result
    assert "Jane Doe" in result
    assert "abcdef12" in result  # truncated sha
    assert git_port.calls == [(Path("/tmp/clone"), "app/foo.py", 1, 5)]


async def test_get_git_blame_tool_handles_missing_local_path() -> None:
    repository = _repository(local_path=None)
    file = _file(repository.id)
    chunk = _chunk(file.id, repository.id)
    tool = GetGitBlameTool(
        FakeChunkRepository(chunk),
        FakeFileRepository(file),
        FakeRepositoryRepository(repository),
        FakeGitPort([]),
    )

    result = await tool(chunk.id)

    assert "not available" in result


async def test_get_git_blame_tool_handles_missing_repository() -> None:
    repository_id = uuid4()
    file = _file(repository_id)
    chunk = _chunk(file.id, repository_id)
    tool = GetGitBlameTool(
        FakeChunkRepository(chunk),
        FakeFileRepository(file),
        FakeRepositoryRepository(None),
        FakeGitPort([]),
    )

    result = await tool(chunk.id)

    assert "not available" in result


async def test_get_git_blame_tool_handles_no_blame_history() -> None:
    repository = _repository(local_path="/tmp/clone")
    file = _file(repository.id)
    chunk = _chunk(file.id, repository.id)
    tool = GetGitBlameTool(
        FakeChunkRepository(chunk),
        FakeFileRepository(file),
        FakeRepositoryRepository(repository),
        FakeGitPort([]),
    )

    result = await tool(chunk.id)

    assert "No blame history" in result
