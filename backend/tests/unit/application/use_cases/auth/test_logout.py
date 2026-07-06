from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.use_cases.auth.logout import LogoutUseCase
from app.core.security import generate_refresh_token
from app.domain.entities.refresh_token import RefreshToken
from tests.unit.application.use_cases.auth.fakes import (
    FakeRefreshTokenRepository,
    FakeTokenBlacklist,
)


async def test_logout_revokes_refresh_token_and_blacklists_access_token_jti() -> None:
    refresh_repo = FakeRefreshTokenRepository()
    blacklist = FakeTokenBlacklist()
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
    await refresh_repo.add(token)
    use_case = LogoutUseCase(refresh_repo, blacklist)
    expires_at = now + timedelta(minutes=10)

    await use_case.execute(
        refresh_token=plain, access_token_jti="jti-123", access_token_expires_at=expires_at
    )

    assert refresh_repo.tokens[token.id].revoked_at is not None
    assert "jti-123" in blacklist.blacklisted
    # TTL should be ~10 minutes (600s), allow a little slack for test execution time.
    assert 590 <= blacklist.blacklisted["jti-123"] <= 600


async def test_logout_blacklists_jti_even_if_refresh_token_unknown() -> None:
    refresh_repo = FakeRefreshTokenRepository()
    blacklist = FakeTokenBlacklist()
    use_case = LogoutUseCase(refresh_repo, blacklist)
    expires_at = datetime.now(UTC) + timedelta(minutes=5)

    await use_case.execute(
        refresh_token="never-issued", access_token_jti="jti-456", access_token_expires_at=expires_at
    )

    assert "jti-456" in blacklist.blacklisted
