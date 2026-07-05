from typing import Protocol
from uuid import UUID

from app.domain.entities.user import User


class UserRepository(Protocol):
    async def add(self, user: User) -> User: ...
    async def get_by_id(self, user_id: UUID) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None: ...
