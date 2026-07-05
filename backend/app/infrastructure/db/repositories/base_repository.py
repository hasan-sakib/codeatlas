from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyRepository:
    """Shared constructor for all concrete repositories — each subclass
    also implements the corresponding domain Protocol port.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
