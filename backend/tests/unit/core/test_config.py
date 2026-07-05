import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    DatabaseSettings,
    SecuritySettings,
    Settings,
    clear_settings_cache,
    get_settings,
)


def test_settings_raises_when_jwt_secret_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECURITY__JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_rejects_unknown_env_var_under_known_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE__URLL", "postgresql+asyncpg://test:test@localhost:5432/test")

    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_is_cached_until_cleared() -> None:
    first = get_settings()
    second = get_settings()
    assert first is second

    clear_settings_cache()
    third = get_settings()
    assert third is not first


def test_default_values_applied_when_optional_vars_absent() -> None:
    settings = Settings()

    assert settings.database.pool_size == 10
    assert settings.security.access_token_expire_minutes == 15
    assert settings.cors_origins == ["http://localhost:3000"]


def test_database_url_rejects_non_postgres_scheme() -> None:
    with pytest.raises(ValidationError):
        DatabaseSettings(url="mysql://user:pass@host/db")  # type: ignore[arg-type]


def test_database_url_accepts_asyncpg_scheme() -> None:
    settings = DatabaseSettings(url="postgresql+asyncpg://user:pass@host:5432/db")  # type: ignore[arg-type]

    assert settings.url.scheme == "postgresql+asyncpg"


def test_jwt_secret_key_never_leaks_in_repr_or_str() -> None:
    settings = SecuritySettings(jwt_secret_key="supersecret")  # type: ignore[arg-type]

    assert "supersecret" not in repr(settings)
    assert "supersecret" not in str(settings.jwt_secret_key)
    assert settings.jwt_secret_key.get_secret_value() == "supersecret"


def test_env_example_loads_successfully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    env_example = repo_root / ".env.example"
    assert env_example.exists(), f"expected {env_example} to exist"

    shutil.copy(env_example, tmp_path / ".env")
    monkeypatch.chdir(tmp_path)
    clear_settings_cache()

    settings = Settings()

    assert settings.environment == "local"
    assert settings.database.url.scheme == "postgresql+asyncpg"
    assert settings.qdrant.collection_prefix == "code_chunks"
    assert settings.ollama.model_name == "qwen3:4b"
