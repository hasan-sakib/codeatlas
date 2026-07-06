from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt as pyjwt
import pytest

from app.core.config import SecuritySettings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


@pytest.fixture
def settings() -> SecuritySettings:
    return SecuritySettings(jwt_secret_key="a-sufficiently-long-test-secret-key-value")  # type: ignore[arg-type]


def test_hash_password_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_hash_password_salts_each_call_differently() -> None:
    first = hash_password("same-password")
    second = hash_password("same-password")

    assert first != second
    assert verify_password("same-password", first)
    assert verify_password("same-password", second)


def test_create_and_decode_access_token_round_trip(settings: SecuritySettings) -> None:
    user_id = uuid4()

    token, jti = create_access_token(user_id, settings)
    claims = decode_access_token(token, settings)

    assert claims.user_id == user_id
    assert claims.jti == jti
    assert claims.expires_at > datetime.now(UTC)
    assert claims.expires_at <= datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes + 1
    )


def test_decode_access_token_rejects_tampered_token(settings: SecuritySettings) -> None:
    token, _jti = create_access_token(uuid4(), settings)

    with pytest.raises(pyjwt.InvalidSignatureError):
        decode_access_token(token + "tampered", settings)


def test_decode_access_token_rejects_wrong_secret(settings: SecuritySettings) -> None:
    token, _jti = create_access_token(uuid4(), settings)
    other_settings = SecuritySettings(jwt_secret_key="a-totally-different-secret-key-value")  # type: ignore[arg-type]

    with pytest.raises(pyjwt.InvalidSignatureError):
        decode_access_token(token, other_settings)


def test_decode_access_token_rejects_expired_token(settings: SecuritySettings) -> None:
    expired_settings = SecuritySettings(  # type: ignore[arg-type]
        jwt_secret_key=settings.jwt_secret_key.get_secret_value(),
        access_token_expire_minutes=-1,
    )
    token, _jti = create_access_token(uuid4(), expired_settings)

    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_access_token(token, settings)


def test_generate_refresh_token_returns_distinct_plaintext_and_matching_hash() -> None:
    plaintext, digest = generate_refresh_token()

    assert plaintext != digest
    assert digest == hash_refresh_token(plaintext)
    # sha256 hex digest is always 64 chars
    assert len(digest) == 64


def test_generate_refresh_token_is_unique_per_call() -> None:
    first_plain, first_hash = generate_refresh_token()
    second_plain, second_hash = generate_refresh_token()

    assert first_plain != second_plain
    assert first_hash != second_hash
