from uuid import UUID

from sqlalchemy import select

from app.domain.entities.file import File
from app.domain.ports.file_repository import FileRepository
from app.infrastructure.db.models.file import FileModel
from app.infrastructure.db.repositories.base_repository import SqlAlchemyRepository


def _to_entity(model: FileModel) -> File:
    return File(
        id=model.id,
        repository_id=model.repository_id,
        path=model.path,
        language=model.language,
        size_bytes=model.size_bytes,
        content_hash=model.content_hash,
        last_commit_sha=model.last_commit_sha,
        last_modified_at=model.last_modified_at,
        is_deleted=model.is_deleted,
        indexed_at=model.indexed_at,
    )


class SqlAlchemyFileRepository(SqlAlchemyRepository, FileRepository):
    async def add(self, file: File) -> File:
        model = FileModel(
            id=file.id,
            repository_id=file.repository_id,
            path=file.path,
            language=file.language,
            size_bytes=file.size_bytes,
            content_hash=file.content_hash,
            last_commit_sha=file.last_commit_sha,
            last_modified_at=file.last_modified_at,
            is_deleted=file.is_deleted,
            indexed_at=file.indexed_at,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)

    async def get_by_id(self, file_id: UUID) -> File | None:
        model = await self.session.get(FileModel, file_id)
        return _to_entity(model) if model else None

    async def get_by_repository_and_path(self, repository_id: UUID, path: str) -> File | None:
        result = await self.session.execute(
            select(FileModel).where(
                FileModel.repository_id == repository_id, FileModel.path == path
            )
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def list_by_repository(self, repository_id: UUID) -> list[File]:
        result = await self.session.execute(
            select(FileModel).where(FileModel.repository_id == repository_id)
        )
        return [_to_entity(m) for m in result.scalars().all()]

    async def upsert(self, file: File) -> File:
        existing_model: FileModel | None = None
        result = await self.session.execute(
            select(FileModel).where(
                FileModel.repository_id == file.repository_id, FileModel.path == file.path
            )
        )
        existing_model = result.scalar_one_or_none()

        if existing_model is None:
            return await self.add(file)

        existing_model.language = file.language
        existing_model.size_bytes = file.size_bytes
        existing_model.content_hash = file.content_hash
        existing_model.last_commit_sha = file.last_commit_sha
        existing_model.last_modified_at = file.last_modified_at
        existing_model.is_deleted = file.is_deleted
        existing_model.indexed_at = file.indexed_at
        await self.session.flush()
        await self.session.refresh(existing_model)
        return _to_entity(existing_model)
