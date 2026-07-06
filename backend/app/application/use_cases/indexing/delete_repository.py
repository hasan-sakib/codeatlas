from uuid import UUID

from app.domain.exceptions import RepositoryNotFoundError
from app.domain.ports.repository_repository import RepositoryRepository


class DeleteRepositoryUseCase:
    """Deletes the Postgres repository row — FK CASCADE (Module 4) removes
    its files/chunks/indexing_jobs.

    Does NOT clean up Qdrant vectors yet: that requires VectorStorePort,
    which doesn't exist until Module 10. Revisit this use case then to add
    `await vector_store.delete_by_filter(workspace_id=..., repository_id=...)`
    after the row delete succeeds (see docs/modules/repository_management.md).
    """

    def __init__(self, repository_repo: RepositoryRepository) -> None:
        self._repository_repo = repository_repo

    async def execute(self, workspace_id: UUID, repository_id: UUID) -> None:
        repository = await self._repository_repo.get_by_id(repository_id)
        if repository is None or repository.workspace_id != workspace_id:
            raise RepositoryNotFoundError()
        await self._repository_repo.delete(repository_id)
