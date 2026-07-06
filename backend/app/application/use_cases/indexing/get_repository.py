from uuid import UUID

from app.domain.entities.repository import Repository
from app.domain.exceptions import RepositoryNotFoundError
from app.domain.ports.repository_repository import RepositoryRepository


class GetRepositoryUseCase:
    """Scoped to workspace_id, not just repository_id — a repository that
    exists but belongs to a different workspace is treated as not found
    (tenant isolation, see DESIGN.md §23), same anti-enumeration rationale
    as GetWorkspaceUseCase.
    """

    def __init__(self, repository_repo: RepositoryRepository) -> None:
        self._repository_repo = repository_repo

    async def execute(self, workspace_id: UUID, repository_id: UUID) -> Repository:
        repository = await self._repository_repo.get_by_id(repository_id)
        if repository is None or repository.workspace_id != workspace_id:
            raise RepositoryNotFoundError()
        return repository
