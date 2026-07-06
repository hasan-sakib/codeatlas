from uuid import UUID

from app.domain.entities.repository import Repository
from app.domain.ports.repository_repository import RepositoryRepository


class ListRepositoriesUseCase:
    def __init__(self, repository_repo: RepositoryRepository) -> None:
        self._repository_repo = repository_repo

    async def execute(self, workspace_id: UUID) -> list[Repository]:
        return await self._repository_repo.list_by_workspace(workspace_id)
