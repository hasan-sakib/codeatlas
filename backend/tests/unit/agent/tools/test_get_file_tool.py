from uuid import uuid4

from app.agent.tools.get_file_tool import GetFileTool
from app.domain.entities.chunk import Chunk, ChunkType, SymbolKind
from app.domain.entities.file import File


class FakeChunkRepository:
    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = {c.id: c for c in chunks}
        self._by_file: dict = {}
        for c in chunks:
            self._by_file.setdefault(c.file_id, []).append(c)

    async def get_by_id(self, chunk_id):
        return self._chunks.get(chunk_id)

    async def list_by_file(self, file_id):
        return self._by_file.get(file_id, [])


class FakeFileRepository:
    def __init__(self, files: list[File]) -> None:
        self._files = {f.id: f for f in files}

    async def get_by_id(self, file_id):
        return self._files.get(file_id)


def _chunk(file_id, start_line, content, is_active=True) -> Chunk:
    return Chunk(
        id=uuid4(),
        file_id=file_id,
        repository_id=uuid4(),
        symbol_name="foo",
        symbol_kind=SymbolKind.FUNCTION,
        start_line=start_line,
        end_line=start_line + 1,
        content=content,
        content_tokens=5,
        chunk_type=ChunkType.CODE,
        is_active=is_active,
    )


def _file(path: str) -> File:
    return File(
        id=uuid4(),
        repository_id=uuid4(),
        path=path,
        language="python",
        size_bytes=10,
        content_hash="abc",
        last_commit_sha=None,
        last_modified_at=None,
        is_deleted=False,
        indexed_at=None,
    )


async def test_get_file_tool_reconstructs_file_from_active_chunks_in_line_order() -> None:
    file = _file("app/foo.py")
    chunk_b = _chunk(file.id, start_line=10, content="def bar(): pass")
    chunk_a = _chunk(file.id, start_line=1, content="def foo(): pass")
    tool = GetFileTool(FakeChunkRepository([chunk_b, chunk_a]), FakeFileRepository([file]))

    result = await tool(chunk_a.id)

    assert result.startswith("app/foo.py:\n")
    assert result.index("def foo") < result.index("def bar")  # ordered by start_line


async def test_get_file_tool_excludes_inactive_chunks() -> None:
    file = _file("app/foo.py")
    active = _chunk(file.id, start_line=1, content="active content")
    inactive = _chunk(file.id, start_line=2, content="stale content", is_active=False)
    tool = GetFileTool(FakeChunkRepository([active, inactive]), FakeFileRepository([file]))

    result = await tool(active.id)

    assert "active content" in result
    assert "stale content" not in result


async def test_get_file_tool_handles_unknown_chunk_id() -> None:
    tool = GetFileTool(FakeChunkRepository([]), FakeFileRepository([]))
    result = await tool(uuid4())
    assert "No chunk found" in result
