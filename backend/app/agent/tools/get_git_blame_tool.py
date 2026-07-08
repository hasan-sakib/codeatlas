from pathlib import Path
from typing import ClassVar
from uuid import UUID

from app.domain.ports.chunk_repository import ChunkRepository
from app.domain.ports.file_repository import FileRepository
from app.domain.ports.git_port import GitPort
from app.domain.ports.repository_repository import RepositoryRepository


class GetGitBlameTool:
    """Blame for the line range of a specific retrieved chunk.

    Requires Repository.local_path to still point at a real clone on
    disk. The full indexing pipeline (clone -> parse -> chunk -> embed)
    doesn't exist yet as an orchestrated whole, so whether a clone
    survives past the initial indexing run is genuinely undetermined at
    this point in the project — this tool surfaces that as a normal
    "not available" result rather than crashing, since a missing clone
    is an expected operational state, not a bug.
    """

    name: ClassVar[str] = "get_git_blame"

    def __init__(
        self,
        chunk_repository: ChunkRepository,
        file_repository: FileRepository,
        repository_repository: RepositoryRepository,
        git_port: GitPort,
    ) -> None:
        self._chunk_repository = chunk_repository
        self._file_repository = file_repository
        self._repository_repository = repository_repository
        self._git_port = git_port

    async def __call__(self, chunk_id: UUID) -> str:
        chunk = await self._chunk_repository.get_by_id(chunk_id)
        if chunk is None:
            return f"No chunk found for id {chunk_id}."

        file = await self._file_repository.get_by_id(chunk.file_id)
        if file is None:
            return f"No file found for chunk {chunk_id}."

        repository = await self._repository_repository.get_by_id(chunk.repository_id)
        if repository is None or not repository.local_path:
            return f"No local clone available for {file.path} — blame is not available."

        entries = await self._git_port.get_blame(
            Path(repository.local_path), file.path, chunk.start_line, chunk.end_line
        )
        if not entries:
            return f"No blame history found for {file.path}:{chunk.start_line}-{chunk.end_line}."

        lines = [f"{e.commit_sha[:8]} {e.author} {e.committed_at.date()}" for e in entries]
        return f"{file.path}:{chunk.start_line}-{chunk.end_line}\n" + "\n".join(lines)
