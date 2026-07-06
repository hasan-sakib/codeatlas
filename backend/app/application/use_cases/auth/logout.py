from datetime import UTC, datetime

from app.core.security import hash_refresh_token
from app.domain.ports.refresh_token_repository import RefreshTokenRepository
from app.domain.ports.token_blacklist import TokenBlacklistPort


class LogoutUseCase:
    def __init__(
        self,
        refresh_token_repo: RefreshTokenRepository,
        blacklist: TokenBlacklistPort,
    ) -> None:
        self._refresh_token_repo = refresh_token_repo
        self._blacklist = blacklist

    async def execute(
        self,
        *,
        refresh_token: str,
        access_token_jti: str,
        access_token_expires_at: datetime,
    ) -> None:
        token_hash = hash_refresh_token(refresh_token)
        existing = await self._refresh_token_repo.get_by_token_hash(token_hash)
        if existing is not None:
            await self._refresh_token_repo.revoke(existing.id)

        ttl_seconds = int((access_token_expires_at - datetime.now(UTC)).total_seconds())
        await self._blacklist.blacklist(access_token_jti, ttl_seconds)
