from datetime import UTC, datetime
from uuid import uuid4

from app.core.security import hash_password
from app.domain.entities.user import User
from app.domain.exceptions import EmailAlreadyExistsError
from app.domain.ports.user_repository import UserRepository


class RegisterUserUseCase:
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, email: str, password: str, full_name: str | None = None) -> User:
        existing = await self._user_repo.get_by_email(email)
        if existing is not None:
            raise EmailAlreadyExistsError(email)

        now = datetime.now(UTC)
        user = User(
            id=uuid4(),
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_active=True,
            is_verified=False,
            created_at=now,
            updated_at=now,
        )
        return await self._user_repo.add(user)
