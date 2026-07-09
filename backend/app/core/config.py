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
    # Ollama's own server-launch default context window is much smaller
    # than the model supports (verified: 4096, vs. qwen3:4b's advertised
    # 262144) — every request must set options.num_ctx explicitly or it
    # silently runs with whatever the server happened to start with.
    # 16384 (verified to load fine, ~5.1GB resident) leaves headroom
    # above generate_answer_max_tokens (4096, Module 13) plus a full RAG
    # prompt (query + history + several chunks).
    num_ctx: int = 16384
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0


class GitSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GIT__", extra="forbid")

    clone_timeout_seconds: float = 120.0
    max_repo_size_mb: int = 500


class ChunkingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHUNKING__", extra="forbid")

    max_chunk_tokens: int = 512
    min_chunk_tokens: int = 64
    merge_target_tokens: int = 256


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMBEDDING__", extra="forbid")

    # The Hugging Face repo actually loaded for inference.
    model_name_or_path: str = "BAAI/bge-m3"
    # The cache-key namespace (see text_normalizer.py) — deliberately
    # separate from model_name_or_path so bumping the embedding version
    # (forcing cache invalidation) doesn't require changing which weights
    # are loaded, and vice versa.
    model_id: str = "bge-m3:v1"
    batch_size: int = 32
    use_fp16: bool = True
    cache_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days — long-lived, see docs


class RerankerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RERANKER__", extra="forbid")

    model_name: str = "BAAI/bge-reranker-base"
    max_length: int = 512
    batch_size: int = 16
    device: str = "cpu"
    # If the cross-encoder fails to load or score (OOM, corrupted cache,
    # etc.), return the input order unchanged instead of failing the
    # whole retrieval request — reranking is a quality improvement, not
    # a correctness requirement.
    fail_open: bool = True


class ConversationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONVERSATION__", extra="forbid")

    # Every Nth turn (assistant + user combined, per increment_turn_count)
    # triggers a re-summarization dispatch.
    summary_threshold: int = 10
    # Default number of recent messages get_context_window()/
    # SummarizeConversationUseCase pull when no caller-specific override
    # is given.
    context_window_turns: int = 20


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT__", extra="forbid")

    max_retrieval_attempts: int = 2
    max_tool_calls: int = 3
    # Widening factor applied to k1/k2 on each retry past the first
    # retrieval attempt (assess_sufficiency's "insufficient" path).
    retry_k_multiplier: int = 2
    # Every LLM call in this agent — even a one-word intent
    # classification — needs generous headroom: Module 14 found Qwen3's
    # default thinking behavior can consume hundreds of tokens before
    # any answer text appears, and a too-small budget silently returns
    # an empty response (finish_reason="length") rather than an error.
    # generate_answer's default is higher still — verified directly that
    # 2048 was NOT always enough for a real RAG prompt (thinking consumed
    # the entire budget, empty answer) even though it comfortably covers
    # a bare intent-classification call; num_ctx (8192 default) must
    # stay comfortably above this plus prompt size.
    classify_intent_max_tokens: int = 1024
    rewrite_query_max_tokens: int = 1024
    generate_answer_max_tokens: int = 4096
    # How many top-N reranked chunks are placed into the generate_answer
    # prompt — separate from RetrievalQuery.n (Module 11), which bounds
    # what the retriever returns before this further slice.
    context_chunk_count: int = 8


class CelerySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CELERY__", extra="forbid")

    # A different Redis DB index than REDIS__URL's default (0) —
    # independently configurable, not silently coupled to the app's own
    # cache/rate-limit/token-blacklist keys, even though both commonly
    # point at the same physical Redis instance in this deployment.
    broker_url: RedisDsn = RedisDsn("redis://localhost:6379/1")
    result_backend: RedisDsn = RedisDsn("redis://localhost:6379/1")


class IndexingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INDEXING__", extra="forbid")

    max_file_size_bytes: int = 1_000_000  # 1MB — larger files are almost never hand-written source
    excluded_dir_names: frozenset[str] = frozenset(
        {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target"}
    )


class RateLimitSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT__", extra="forbid")

    auth_per_ip_per_minute: int = 5
    chat_per_user_per_minute: int = 30
    indexing_trigger_per_user_per_minute: int = 3


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
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    reranker: RerankerSettings = Field(default_factory=RerankerSettings)
    conversation: ConversationSettings = Field(default_factory=ConversationSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    indexing: IndexingSettings = Field(default_factory=IndexingSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # database/qdrant/redis/ollama/security are populated from env vars via
    # env_nested_delimiter, not passed as kwargs — mypy can't see that.
    return Settings()  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    get_settings.cache_clear()
