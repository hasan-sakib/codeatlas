import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import SecuritySettings

_password_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _password_hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _password_hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    jti: str
    expires_at: datetime


def create_access_token(user_id: UUID, settings: SecuritySettings) -> tuple[str, str]:
    """Returns (encoded_token, jti)."""
    jti = str(uuid4())
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "jti": jti, "exp": expires_at}
    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, jti


def decode_access_token(token: str, settings: SecuritySettings) -> AccessTokenClaims:
    """Raises jwt.PyJWTError (or a subclass) on any invalid/expired/tampered token."""
    payload = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )
    return AccessTokenClaims(
        user_id=UUID(payload["sub"]),
        jti=payload["jti"],
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )


def generate_refresh_token() -> tuple[str, str]:
    """Returns (plaintext, sha256_hash). Only the hash is ever persisted —
    the plaintext is returned to the caller once and never stored."""
    plaintext = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, token_hash


def hash_refresh_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()
