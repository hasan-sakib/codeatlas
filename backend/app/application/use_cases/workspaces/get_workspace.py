from uuid import UUID

from app.domain.entities.workspace import Workspace
from app.domain.exceptions import WorkspaceNotFoundError
from app.domain.ports.workspace_repository import WorkspaceRepository


class GetWorkspaceUseCase:
    """Also the sole place the "does this workspace exist and is it mine"
    business rule lives — app/api/deps.py's require_workspace_access is a
    thin FastAPI-specific wrapper around this use case.
    """

    def __init__(self, workspace_repo: WorkspaceRepository) -> None:
        self._workspace_repo = workspace_repo

    async def execute(self, workspace_id: UUID, requesting_user_id: UUID) -> Workspace:
        workspace = await self._workspace_repo.get_by_id(workspace_id)
        if workspace is None or workspace.owner_id != requesting_user_id:
            raise WorkspaceNotFoundError()
        return workspace
