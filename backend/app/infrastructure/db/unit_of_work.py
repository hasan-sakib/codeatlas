from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork:
    """Explicit commit/rollback wrapper around a session, for use cases
    that need multiple repository writes to share one transaction (e.g.
    persisting files + chunks atomically during indexing).

    Unlike get_db_session() (which auto-commits on success), UnitOfWork
    requires an explicit .commit() call inside the `async with` block —
    it only ever rolls back automatically, on exception.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> "UnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
