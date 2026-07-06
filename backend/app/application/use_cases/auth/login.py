from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.config import SecuritySettings
from app.core.security import create_access_token, generate_refresh_token, verify_password
from app.domain.entities.refresh_token import RefreshToken
from app.domain.exceptions import InvalidCredentialsError
from app.domain.ports.refresh_token_repository import RefreshTokenRepository
from app.domain.ports.user_repository import UserRepository
from app.domain.value_objects.token_pair import TokenPair


class LoginUseCase:
    def __init__(
        self,
        user_repo: UserRepository,
        refresh_token_repo: RefreshTokenRepository,
        settings: SecuritySettings,
    ) -> None:
        self._user_repo = user_repo
        self._refresh_token_repo = refresh_token_repo
        self._settings = settings

    async def execute(self, email: str, password: str) -> TokenPair:
        user = await self._user_repo.get_by_email(email)
        # Same generic error whether the email doesn't exist or the
        # password is wrong — no signal that would let an attacker
        # enumerate registered emails.
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()

        return await issue_token_pair(user.id, self._refresh_token_repo, self._settings)


async def issue_token_pair(
    user_id: UUID,
    refresh_token_repo: RefreshTokenRepository,
    settings: SecuritySettings,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> TokenPair:
    """Shared by LoginUseCase and RefreshTokenUseCase — both need to mint
    a fresh access+refresh pair the same way."""
    access_token, _jti = create_access_token(user_id, settings)
    refresh_plain, refresh_hash = generate_refresh_token()
    now = datetime.now(UTC)
    await refresh_token_repo.add(
        RefreshToken(
            id=uuid4(),
            user_id=user_id,
            token_hash=refresh_hash,
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
            revoked_at=None,
            user_agent=user_agent,
            ip=ip,
            created_at=now,
        )
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_plain)
