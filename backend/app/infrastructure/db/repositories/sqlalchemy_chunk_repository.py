from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select, update

from app.domain.entities.chunk import Chunk
from app.domain.ports.chunk_repository import ChunkRepository
from app.infrastructure.db.models.chunk import ChunkModel
from app.infrastructure.db.repositories.base_repository import SqlAlchemyRepository


def _to_entity(model: ChunkModel) -> Chunk:
    return Chunk(
        id=model.id,
        file_id=model.file_id,
        repository_id=model.repository_id,
        symbol_name=model.symbol_name,
        symbol_kind=model.symbol_kind,
        start_line=model.start_line,
        end_line=model.end_line,
        content=model.content,
        content_tokens=model.content_tokens,
        chunk_type=model.chunk_type,
        imports=list(model.imports or []),
        git_blame=model.git_blame,
        embedding_model=model.embedding_model,
        embedding_version=model.embedding_version,
        is_active=model.is_active,
        created_at=model.created_at,
    )


class SqlAlchemyChunkRepository(SqlAlchemyRepository, ChunkRepository):
    async def add_many(self, chunks: Sequence[Chunk]) -> None:
        models = [
            ChunkModel(
                id=chunk.id,
                file_id=chunk.file_id,
                repository_id=chunk.repository_id,
                symbol_name=chunk.symbol_name,
                symbol_kind=chunk.symbol_kind,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content=chunk.content,
                content_tokens=chunk.content_tokens,
                chunk_type=chunk.chunk_type,
                imports=chunk.imports,
                git_blame=chunk.git_blame,
                embedding_model=chunk.embedding_model,
                embedding_version=chunk.embedding_version,
                is_active=chunk.is_active,
            )
            for chunk in chunks
        ]
        self.session.add_all(models)
        await self.session.flush()

    async def get_by_id(self, chunk_id: UUID) -> Chunk | None:
        model = await self.session.get(ChunkModel, chunk_id)
        return _to_entity(model) if model else None

    async def get_by_ids(self, chunk_ids: Sequence[UUID]) -> list[Chunk]:
        if not chunk_ids:
            return []
        result = await self.session.execute(select(ChunkModel).where(ChunkModel.id.in_(chunk_ids)))
        return [_to_entity(m) for m in result.scalars().all()]

    async def list_by_file(self, file_id: UUID) -> list[Chunk]:
        result = await self.session.execute(select(ChunkModel).where(ChunkModel.file_id == file_id))
        return [_to_entity(m) for m in result.scalars().all()]

    async def deactivate_by_file(self, file_id: UUID) -> None:
        await self.session.execute(
            update(ChunkModel).where(ChunkModel.file_id == file_id).values(is_active=False)
        )

    async def delete_by_file(self, file_id: UUID) -> None:
        await self.session.execute(delete(ChunkModel).where(ChunkModel.file_id == file_id))

    async def delete_by_repository(self, repository_id: UUID) -> None:
        await self.session.execute(
            delete(ChunkModel).where(ChunkModel.repository_id == repository_id)
        )
