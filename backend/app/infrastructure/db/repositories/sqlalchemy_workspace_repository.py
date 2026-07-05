from uuid import UUID

from sqlalchemy import select

from app.domain.entities.workspace import Workspace
from app.domain.ports.workspace_repository import WorkspaceRepository
from app.infrastructure.db.models.workspace import WorkspaceModel
from app.infrastructure.db.repositories.base_repository import SqlAlchemyRepository


def _to_entity(model: WorkspaceModel) -> Workspace:
    return Workspace(
        id=model.id,
        owner_id=model.owner_id,
        name=model.name,
        slug=model.slug,
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyWorkspaceRepository(SqlAlchemyRepository, WorkspaceRepository):
    async def add(self, workspace: Workspace) -> Workspace:
        model = WorkspaceModel(
            id=workspace.id,
            owner_id=workspace.owner_id,
            name=workspace.name,
            slug=workspace.slug,
            description=workspace.description,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)

    async def get_by_id(self, workspace_id: UUID) -> Workspace | None:
        model = await self.session.get(WorkspaceModel, workspace_id)
        return _to_entity(model) if model else None

    async def list_for_owner(self, owner_id: UUID) -> list[Workspace]:
        result = await self.session.execute(
            select(WorkspaceModel).where(WorkspaceModel.owner_id == owner_id)
        )
        return [_to_entity(m) for m in result.scalars().all()]

    async def delete(self, workspace_id: UUID) -> None:
        model = await self.session.get(WorkspaceModel, workspace_id)
        if model is not None:
            await self.session.delete(model)
