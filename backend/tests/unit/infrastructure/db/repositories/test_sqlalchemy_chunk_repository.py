from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.domain.entities.chunk import Chunk, ChunkType, SymbolKind
from app.infrastructure.db.repositories.sqlalchemy_chunk_repository import (
    SqlAlchemyChunkRepository,
)


def _make_chunk(**overrides: object) -> Chunk:
    defaults: dict[str, object] = dict(
        id=uuid4(),
        file_id=uuid4(),
        repository_id=uuid4(),
        symbol_name="my_function",
        symbol_kind=SymbolKind.FUNCTION,
        start_line=1,
        end_line=10,
        content="def my_function(): ...",
        content_tokens=5,
        chunk_type=ChunkType.CODE,
    )
    defaults.update(overrides)
    return Chunk(**defaults)  # type: ignore[arg-type]


async def test_add_many_builds_correct_orm_instances_and_flushes() -> None:
    session = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    repo = SqlAlchemyChunkRepository(session)

    chunk = _make_chunk()
    await repo.add_many([chunk])

    session.add_all.assert_called_once()
    (models,) = session.add_all.call_args.args
    assert len(models) == 1
    model = models[0]
    assert model.id == chunk.id
    assert model.file_id == chunk.file_id
    assert model.symbol_name == "my_function"
    assert model.symbol_kind == SymbolKind.FUNCTION
    assert model.content == "def my_function(): ..."
    session.flush.assert_awaited_once()


async def test_add_many_with_empty_sequence_still_calls_add_all() -> None:
    session = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    repo = SqlAlchemyChunkRepository(session)

    await repo.add_many([])

    session.add_all.assert_called_once_with([])
    session.flush.assert_awaited_once()


async def test_get_by_id_returns_none_when_session_get_returns_none() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    repo = SqlAlchemyChunkRepository(session)

    result = await repo.get_by_id(uuid4())

    assert result is None
    session.get.assert_awaited_once()


async def test_get_by_ids_with_empty_sequence_does_not_query() -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    repo = SqlAlchemyChunkRepository(session)

    result = await repo.get_by_ids([])

    assert result == []
    session.execute.assert_not_awaited()
