from uuid import UUID

from app.domain.entities.workspace import Workspace


class FakeWorkspaceRepository:
    def __init__(self) -> None:
        self.workspaces: dict[UUID, Workspace] = {}

    async def add(self, workspace: Workspace) -> Workspace:
        self.workspaces[workspace.id] = workspace
        return workspace

    async def get_by_id(self, workspace_id: UUID) -> Workspace | None:
        return self.workspaces.get(workspace_id)

    async def list_for_owner(self, owner_id: UUID) -> list[Workspace]:
        return [w for w in self.workspaces.values() if w.owner_id == owner_id]

    async def delete(self, workspace_id: UUID) -> None:
        self.workspaces.pop(workspace_id, None)
