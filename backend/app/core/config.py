from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE__", extra="forbid")

    url: PostgresDsn
    pool_size: int = 10
    max_overflow: int = 5
    echo: bool = False


class QdrantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QDRANT__", extra="forbid")

    url: AnyHttpUrl
    api_key: SecretStr | None = None
    collection_prefix: str = "code_chunks"
    timeout_seconds: float = 30.0


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS__", extra="forbid")

    url: RedisDsn
    cache_ttl_seconds: int = 3600


class OllamaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OLLAMA__", extra="forbid")

    base_url: AnyHttpUrl
    model_name: str = "qwen3:4b"
    request_timeout_seconds: float = 120.0


class GitSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GIT__", extra="forbid")

    clone_timeout_seconds: float = 120.0
    max_repo_size_mb: int = 500


class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SECURITY__", extra="forbid")

    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env lives at the repo root (see bootstrap.sh, docker-compose.yml's
        # env_file directive); check both so this resolves whether the
        # process is launched from the repo root or from backend/.
        env_file=(".env", "../.env"),
        env_nested_delimiter="__",
        extra="forbid",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]

    database: DatabaseSettings
    qdrant: QdrantSettings
    redis: RedisSettings
    ollama: OllamaSettings
    security: SecuritySettings
    # All fields have sane defaults, unlike the other nested settings —
    # explicit default_factory so a deployment need not set any GIT__ env
    # var at all. Factory (not a bare instance) so it re-reads the
    # environment at each Settings() construction, matching the
    # clear_settings_cache()-then-monkeypatch test pattern used elsewhere.
    git: GitSettings = Field(default_factory=GitSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # database/qdrant/redis/ollama/security are populated from env vars via
    # env_nested_delimiter, not passed as kwargs — mypy can't see that.
    return Settings()  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    get_settings.cache_clear()
