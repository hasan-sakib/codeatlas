import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.infrastructure.db.models  # noqa: F401  registers all tables on Base.metadata
from app.application.use_cases.auth.refresh_token import RefreshTokenUseCase
from app.core.config import SecuritySettings
from app.core.security import generate_refresh_token
from app.domain.entities.refresh_token import RefreshToken
from app.domain.entities.user import User
from app.domain.exceptions import InvalidRefreshTokenError
from app.infrastructure.db.base import Base
from app.infrastructure.db.repositories.sqlalchemy_refresh_token_repository import (
    SqlAlchemyRefreshTokenRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)

pytestmark = pytest.mark.integration


async def test_concurrent_refresh_of_same_token_only_one_call_succeeds(postgres_container) -> None:
    # Deliberately bypasses the app's cached engine/sessionmaker (and the
    # `db_session`/`api_client` fixtures) — this test needs two genuinely
    # independent DB sessions/connections racing on the same row, which a
    # single shared AsyncSession can't exercise (it only does one
    # statement at a time).
    engine = create_async_engine(postgres_container.get_connection_url())
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        settings = SecuritySettings(  # type: ignore[arg-type]
            jwt_secret_key="integration-test-secret-key-value"
        )

        plain, digest = generate_refresh_token()
        now = datetime.now(UTC)
        async with sessionmaker() as seed_session:
            user = await SqlAlchemyUserRepository(seed_session).add(
                User(
                    id=uuid4(),
                    email=f"{uuid4()}@example.com",
                    hashed_password="irrelevant",
                    full_name=None,
                    is_active=True,
                    is_verified=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            await SqlAlchemyRefreshTokenRepository(seed_session).add(
                RefreshToken(
                    id=uuid4(),
                    user_id=user.id,
                    token_hash=digest,
                    expires_at=now + timedelta(days=30),
                    revoked_at=None,
                    user_agent=None,
                    ip=None,
                    created_at=now,
                )
            )
            await seed_session.commit()

        async def _attempt() -> str:
            async with sessionmaker() as session:
                repo = SqlAlchemyRefreshTokenRepository(session)
                use_case = RefreshTokenUseCase(repo, settings)
                try:
                    await use_case.execute(plain)
                except InvalidRefreshTokenError:
                    await session.rollback()
                    return "rejected"
                else:
                    await session.commit()
                    return "success"

        results = await asyncio.gather(_attempt(), _attempt())

        assert sorted(results) == ["rejected", "success"]
    finally:
        await engine.dispose()
