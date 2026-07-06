from datetime import UTC, datetime

from app.application.use_cases.auth.login import issue_token_pair
from app.core.config import SecuritySettings
from app.core.security import hash_refresh_token
from app.domain.exceptions import InvalidRefreshTokenError
from app.domain.ports.refresh_token_repository import RefreshTokenRepository
from app.domain.value_objects.token_pair import TokenPair


class RefreshTokenUseCase:
    def __init__(
        self,
        refresh_token_repo: RefreshTokenRepository,
        settings: SecuritySettings,
    ) -> None:
        self._refresh_token_repo = refresh_token_repo
        self._settings = settings

    async def execute(self, refresh_token: str) -> TokenPair:
        token_hash = hash_refresh_token(refresh_token)
        existing = await self._refresh_token_repo.get_by_token_hash(token_hash)
        if existing is None or existing.expires_at < datetime.now(UTC):
            raise InvalidRefreshTokenError()

        # Atomic compare-and-swap: only the caller that actually flips
        # revoked_at from NULL wins. If two requests race on the same
        # refresh token, the loser gets False here (not a stale read of
        # "still active") — see RefreshTokenRepository.revoke_if_active.
        revoked = await self._refresh_token_repo.revoke_if_active(existing.id)
        if not revoked:
            raise InvalidRefreshTokenError()

        return await issue_token_pair(
            existing.user_id,
            self._refresh_token_repo,
            self._settings,
            user_agent=existing.user_agent,
            ip=existing.ip,
        )
