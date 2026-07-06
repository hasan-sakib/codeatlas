from uuid import UUID

from app.domain.entities.workspace import Workspace
from app.domain.ports.workspace_repository import WorkspaceRepository


class ListWorkspacesUseCase:
    def __init__(self, workspace_repo: WorkspaceRepository) -> None:
        self._workspace_repo = workspace_repo

    async def execute(self, owner_id: UUID) -> list[Workspace]:
        return await self._workspace_repo.list_for_owner(owner_id)
