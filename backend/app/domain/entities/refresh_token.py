from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class RefreshToken:
    id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None
    user_agent: str | None
    ip: str | None
    created_at: datetime

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
