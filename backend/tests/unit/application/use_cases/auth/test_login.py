import pytest

from app.application.use_cases.auth.login import LoginUseCase
from app.application.use_cases.auth.register_user import RegisterUserUseCase
from app.core.config import SecuritySettings
from app.domain.exceptions import InvalidCredentialsError
from tests.unit.application.use_cases.auth.fakes import (
    FakeRefreshTokenRepository,
    FakeUserRepository,
)


@pytest.fixture
def settings() -> SecuritySettings:
    return SecuritySettings(jwt_secret_key="a-sufficiently-long-test-secret-key-value")  # type: ignore[arg-type]


async def test_login_with_wrong_email_raises_invalid_credentials(
    settings: SecuritySettings,
) -> None:
    user_repo = FakeUserRepository()
    refresh_repo = FakeRefreshTokenRepository()
    use_case = LoginUseCase(user_repo, refresh_repo, settings)

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute("nobody@example.com", "irrelevant")


async def test_login_with_wrong_password_raises_invalid_credentials(
    settings: SecuritySettings,
) -> None:
    user_repo = FakeUserRepository()
    refresh_repo = FakeRefreshTokenRepository()
    await RegisterUserUseCase(user_repo).execute("amina@example.com", "correct-password")
    use_case = LoginUseCase(user_repo, refresh_repo, settings)

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute("amina@example.com", "wrong-password")


async def test_login_with_correct_credentials_returns_tokens_and_persists_one_refresh_row(
    settings: SecuritySettings,
) -> None:
    user_repo = FakeUserRepository()
    refresh_repo = FakeRefreshTokenRepository()
    user = await RegisterUserUseCase(user_repo).execute("amina@example.com", "correct-password")
    use_case = LoginUseCase(user_repo, refresh_repo, settings)

    tokens = await use_case.execute("amina@example.com", "correct-password")

    assert tokens.access_token
    assert tokens.refresh_token
    assert refresh_repo.add_call_count == 1
    (stored,) = refresh_repo.tokens.values()
    assert stored.user_id == user.id
    assert stored.revoked_at is None
