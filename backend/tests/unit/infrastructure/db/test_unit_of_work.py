from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.db.unit_of_work import UnitOfWork


async def test_rolls_back_on_exception_and_does_not_commit() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    with pytest.raises(ValueError):
        async with UnitOfWork(session):
            raise ValueError("boom")

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


async def test_does_not_auto_commit_or_rollback_on_clean_exit() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    async with UnitOfWork(session):
        pass

    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


async def test_explicit_commit_calls_session_commit() -> None:
    session = MagicMock()
    session.commit = AsyncMock()

    async with UnitOfWork(session) as uow:
        await uow.commit()

    session.commit.assert_awaited_once()
