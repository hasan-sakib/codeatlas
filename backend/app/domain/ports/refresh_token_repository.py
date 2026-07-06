from typing import Protocol
from uuid import UUID

from app.domain.entities.refresh_token import RefreshToken


class RefreshTokenRepository(Protocol):
    async def add(self, token: RefreshToken) -> RefreshToken: ...
    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None: ...
    async def revoke(self, token_id: UUID) -> None: ...
    async def revoke_all_for_user(self, user_id: UUID) -> None: ...

    async def revoke_if_active(self, token_id: UUID) -> bool:
        """Atomically revoke iff still active (revoked_at IS NULL),
        returning whether this call was the one that revoked it.

        Used by refresh-token rotation to close a TOCTOU race: reading a
        token's active state and revoking it as two separate steps lets
        two concurrent requests both see "active" and both rotate the
        same token. A single conditional UPDATE relies on Postgres
        row-level locking so only one concurrent caller can win.
        """
        ...
