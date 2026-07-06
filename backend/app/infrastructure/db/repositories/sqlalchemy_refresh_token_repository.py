from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult

from app.domain.entities.refresh_token import RefreshToken
from app.domain.ports.refresh_token_repository import RefreshTokenRepository
from app.infrastructure.db.models.refresh_token import RefreshTokenModel
from app.infrastructure.db.repositories.base_repository import SqlAlchemyRepository


def _to_entity(model: RefreshTokenModel) -> RefreshToken:
    return RefreshToken(
        id=model.id,
        user_id=model.user_id,
        token_hash=model.token_hash,
        expires_at=model.expires_at,
        revoked_at=model.revoked_at,
        user_agent=model.user_agent,
        ip=model.ip,
        created_at=model.created_at,
    )


class SqlAlchemyRefreshTokenRepository(SqlAlchemyRepository, RefreshTokenRepository):
    async def add(self, token: RefreshToken) -> RefreshToken:
        model = RefreshTokenModel(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            revoked_at=token.revoked_at,
            user_agent=token.user_agent,
            ip=token.ip,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def revoke(self, token_id: UUID) -> None:
        await self.session.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.id == token_id)
            .values(revoked_at=datetime.now(UTC))
        )

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        await self.session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )

    async def revoke_if_active(self, token_id: UUID) -> bool:
        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(RefreshTokenModel)
                .where(
                    RefreshTokenModel.id == token_id,
                    RefreshTokenModel.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            ),
        )
        return result.rowcount > 0
