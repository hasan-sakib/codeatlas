from uuid import UUID

from sqlalchemy import select

from app.domain.entities.repository import Repository, RepositoryStatus
from app.domain.ports.repository_repository import RepositoryRepository
from app.infrastructure.db.models.repository import RepositoryModel
from app.infrastructure.db.repositories.base_repository import SqlAlchemyRepository


def _to_entity(model: RepositoryModel) -> Repository:
    return Repository(
        id=model.id,
        workspace_id=model.workspace_id,
        source_type=model.source_type,
        git_url=model.git_url,
        default_branch=model.default_branch,
        local_path=model.local_path,
        last_indexed_commit_sha=model.last_indexed_commit_sha,
        status=model.status,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyRepositoryRepository(SqlAlchemyRepository, RepositoryRepository):
    async def add(self, repository: Repository) -> Repository:
        model = RepositoryModel(
            id=repository.id,
            workspace_id=repository.workspace_id,
            source_type=repository.source_type,
            git_url=repository.git_url,
            default_branch=repository.default_branch,
            local_path=repository.local_path,
            last_indexed_commit_sha=repository.last_indexed_commit_sha,
            status=repository.status,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)

    async def get_by_id(self, repository_id: UUID) -> Repository | None:
        model = await self.session.get(RepositoryModel, repository_id)
        return _to_entity(model) if model else None

    async def list_by_workspace(self, workspace_id: UUID) -> list[Repository]:
        result = await self.session.execute(
            select(RepositoryModel).where(RepositoryModel.workspace_id == workspace_id)
        )
        return [_to_entity(m) for m in result.scalars().all()]

    async def update_status(
        self,
        repository_id: UUID,
        status: RepositoryStatus,
        *,
        last_indexed_commit_sha: str | None = None,
    ) -> None:
        model = await self.session.get(RepositoryModel, repository_id)
        if model is None:
            return
        model.status = status
        if last_indexed_commit_sha is not None:
            model.last_indexed_commit_sha = last_indexed_commit_sha

    async def delete(self, repository_id: UUID) -> None:
        model = await self.session.get(RepositoryModel, repository_id)
        if model is not None:
            await self.session.delete(model)
