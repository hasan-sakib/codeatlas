from typing import ClassVar
from uuid import UUID

from app.domain.ports.chunk_repository import ChunkRepository
from app.domain.ports.file_repository import FileRepository


class GetFileTool:
    """Reconstructs a file's content from its active chunks, ordered by
    start_line.

    This is a best-effort reconstruction, not a byte-exact read of the
    original file: Module 8's AST chunker guarantees zero gaps/overlaps
    between a file's chunks by construction, but joining chunk text with
    a blank line loses the exact original inter-chunk whitespace. Good
    enough for giving an LLM surrounding context it didn't get from a
    single retrieved chunk; not a substitute for reading the real file
    off disk (no use case for that exists yet).
    """

    name: ClassVar[str] = "get_file"

    def __init__(self, chunk_repository: ChunkRepository, file_repository: FileRepository) -> None:
        self._chunk_repository = chunk_repository
        self._file_repository = file_repository

    async def __call__(self, chunk_id: UUID) -> str:
        chunk = await self._chunk_repository.get_by_id(chunk_id)
        if chunk is None:
            return f"No chunk found for id {chunk_id}."

        file = await self._file_repository.get_by_id(chunk.file_id)
        if file is None:
            return f"No file found for chunk {chunk_id}."

        chunks = await self._chunk_repository.list_by_file(file.id)
        active = sorted((c for c in chunks if c.is_active), key=lambda c: c.start_line)
        if not active:
            return f"No active chunks found for {file.path}."

        body = "\n\n".join(c.content for c in active)
        return f"{file.path}:\n{body}"
