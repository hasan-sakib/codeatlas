from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from app.domain.entities.refresh_token import RefreshToken
from app.domain.entities.user import User


class FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}

    async def add(self, user: User) -> User:
        self.users[user.id] = user
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        for user in self.users.values():
            if user.email == email:
                return user
        return None


class FakeRefreshTokenRepository:
    def __init__(self) -> None:
        self.tokens: dict[UUID, RefreshToken] = {}
        self.add_call_count = 0

    async def add(self, token: RefreshToken) -> RefreshToken:
        self.add_call_count += 1
        self.tokens[token.id] = token
        return token

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        for token in self.tokens.values():
            if token.token_hash == token_hash:
                return token
        return None

    async def revoke(self, token_id: UUID) -> None:
        token = self.tokens.get(token_id)
        if token is not None:
            self.tokens[token_id] = replace(token, revoked_at=datetime.now(UTC))

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        for token_id, token in list(self.tokens.items()):
            if token.user_id == user_id and token.revoked_at is None:
                self.tokens[token_id] = replace(token, revoked_at=datetime.now(UTC))

    async def revoke_if_active(self, token_id: UUID) -> bool:
        token = self.tokens.get(token_id)
        if token is None or token.revoked_at is not None:
            return False
        self.tokens[token_id] = replace(token, revoked_at=datetime.now(UTC))
        return True


class FakeTokenBlacklist:
    def __init__(self) -> None:
        self.blacklisted: dict[str, int] = {}

    async def blacklist(self, jti: str, ttl_seconds: int) -> None:
        self.blacklisted[jti] = ttl_seconds

    async def is_blacklisted(self, jti: str) -> bool:
        return jti in self.blacklisted
