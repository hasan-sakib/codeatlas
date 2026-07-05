from uuid import UUID

from sqlalchemy import select

from app.domain.entities.user import User
from app.domain.ports.user_repository import UserRepository
from app.infrastructure.db.models.user import UserModel
from app.infrastructure.db.repositories.base_repository import SqlAlchemyRepository


def _to_entity(model: UserModel) -> User:
    return User(
        id=model.id,
        email=model.email,
        hashed_password=model.hashed_password,
        full_name=model.full_name,
        is_active=model.is_active,
        is_verified=model.is_verified,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyUserRepository(SqlAlchemyRepository, UserRepository):
    async def add(self, user: User) -> User:
        model = UserModel(
            id=user.id,
            email=user.email,
            hashed_password=user.hashed_password,
            full_name=user.full_name,
            is_active=user.is_active,
            is_verified=user.is_verified,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)

    async def get_by_id(self, user_id: UUID) -> User | None:
        model = await self.session.get(UserModel, user_id)
        return _to_entity(model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(UserModel).where(UserModel.email == email))
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None
