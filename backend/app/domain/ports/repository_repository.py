from typing import Protocol
from uuid import UUID

from app.domain.entities.repository import Repository, RepositoryStatus


class RepositoryRepository(Protocol):
    async def add(self, repository: Repository) -> Repository: ...
    async def get_by_id(self, repository_id: UUID) -> Repository | None: ...
    async def list_by_workspace(self, workspace_id: UUID) -> list[Repository]: ...
    async def update_status(
        self,
        repository_id: UUID,
        status: RepositoryStatus,
        *,
        last_indexed_commit_sha: str | None = None,
    ) -> None: ...
    async def delete(self, repository_id: UUID) -> None: ...
