from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.application.use_cases.auth.refresh_token import RefreshTokenUseCase
from app.core.config import SecuritySettings
from app.core.security import generate_refresh_token
from app.domain.entities.refresh_token import RefreshToken
from app.domain.exceptions import InvalidRefreshTokenError
from tests.unit.application.use_cases.auth.fakes import FakeRefreshTokenRepository


@pytest.fixture
def settings() -> SecuritySettings:
    return SecuritySettings(jwt_secret_key="a-sufficiently-long-test-secret-key-value")  # type: ignore[arg-type]


async def _seed_active_token(repo: FakeRefreshTokenRepository, **overrides: object) -> str:
    plain, digest = generate_refresh_token()
    now = datetime.now(UTC)
    token = RefreshToken(
        id=uuid4(),
        user_id=uuid4(),
        token_hash=digest,
        expires_at=now + timedelta(days=30),
        revoked_at=None,
        user_agent=None,
        ip=None,
        created_at=now,
    )
    if overrides:
        token = replace(token, **overrides)
    await repo.add(token)
    return plain


async def test_valid_refresh_token_rotates_and_returns_new_pair(settings: SecuritySettings) -> None:
    repo = FakeRefreshTokenRepository()
    plain = await _seed_active_token(repo)
    (old_token,) = list(repo.tokens.values())
    use_case = RefreshTokenUseCase(repo, settings)

    new_tokens = await use_case.execute(plain)

    assert new_tokens.access_token
    assert new_tokens.refresh_token != plain
    assert repo.tokens[old_token.id].revoked_at is not None
    assert repo.add_call_count == 2  # original seed + rotated


async def test_reusing_already_revoked_token_raises(settings: SecuritySettings) -> None:
    repo = FakeRefreshTokenRepository()
    plain = await _seed_active_token(repo)
    use_case = RefreshTokenUseCase(repo, settings)
    await use_case.execute(plain)  # first use rotates it

    with pytest.raises(InvalidRefreshTokenError):
        await use_case.execute(plain)  # second use of the now-revoked token


async def test_expired_token_raises(settings: SecuritySettings) -> None:
    repo = FakeRefreshTokenRepository()
    plain = await _seed_active_token(repo, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    use_case = RefreshTokenUseCase(repo, settings)

    with pytest.raises(InvalidRefreshTokenError):
        await use_case.execute(plain)


async def test_unknown_token_raises(settings: SecuritySettings) -> None:
    repo = FakeRefreshTokenRepository()
    use_case = RefreshTokenUseCase(repo, settings)

    with pytest.raises(InvalidRefreshTokenError):
        await use_case.execute("this-token-was-never-issued")
