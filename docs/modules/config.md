# Module 2: Configuration System

## Settings hierarchy

```
Settings                        (env_file=(".env", "../.env"), env_nested_delimiter="__")
├── environment: local|test|staging|production
├── log_level: str
├── cors_origins: list[str]
├── database: DatabaseSettings  (env_prefix="DATABASE__")
├── qdrant:   QdrantSettings    (env_prefix="QDRANT__")
├── redis:    RedisSettings     (env_prefix="REDIS__")
├── ollama:   OllamaSettings    (env_prefix="OLLAMA__")
└── security: SecuritySettings  (env_prefix="SECURITY__")
```

Each nested class lives in `app/core/config.py`. All are `pydantic_settings.BaseSettings` subclasses with `extra="forbid"`, so a typoed env var (e.g. `DATABASE__URLL`) raises a `pydantic.ValidationError` at startup instead of being silently ignored.

## Precedence order

1. Explicit constructor kwargs (only relevant in tests — production code never passes these)
2. Process environment variables (`os.environ`)
3. `.env` file, checked at both `./.env` and `../.env` relative to the process's working directory
4. Field defaults

Environment variables always win over `.env` file values.

## Why nested settings classes don't each declare `env_file`

Early implementation gave every nested class (`DatabaseSettings`, `QdrantSettings`, etc.) its own `env_file=".env"`, matching a naive reading of "each concern owns its own settings." This broke in practice: when a nested `BaseSettings` field independently loads the same `.env` file, it does **not** filter by its own `env_prefix` first — it sees every key in the file and raises `extra_forbidden` for all the ones that belong to sibling settings classes (confirmed by an actual failing test run, not by inspection).

The fix: only the outer `Settings` class declares `env_file`. It uses `env_nested_delimiter="__"` to parse `DATABASE__URL=...` into the nested dict `{"database": {"url": ...}}`, and pydantic then validates that dict against `DatabaseSettings` — which is where `env_prefix`/`extra="forbid"` correctly apply, scoped to just that nested key. Nested settings classes are never constructed standalone from `.env`/env in this codebase; they're always obtained via `get_settings().database`, etc.

## Why `.env` is checked at two relative paths

`bootstrap.sh` and `docker-compose.yml`'s `env_file: ../../.env` directive both treat the **repo root** as the canonical location for `.env`. But the backend is typically run with CWD set to `backend/` (per the README's `cd backend && uv run uvicorn ...`). A single relative `env_file=".env"` would only ever find `backend/.env`, which doesn't exist. `env_file=(".env", "../.env")` checks both locations; pydantic-settings silently skips whichever one is missing. Verified by booting the real app from both `backend/` and the repo root.

## Fail-fast contract

`get_settings()` (in `app/core/di.py`-equivalent role for now — this module is the sole config touchpoint) is called inside `create_app()`. If a required field is missing (most commonly `SECURITY__JWT_SECRET_KEY`, since it has no default), `Settings()` raises `pydantic.ValidationError` immediately — the process never reaches "serving traffic" state. Verified by booting the app with an empty environment (raises) and with `.env.example`-derived values (succeeds).

## Adding a new settings field

1. Add the field to the relevant nested class (or `Settings` directly for app-level values).
2. Add the corresponding `SECTION__FIELD_NAME=` line to `.env.example` with a safe default/placeholder.
3. Document it here if it needs explanation beyond its name.

## Test-time overrides

Tests never rely on a real `.env` file. `backend/tests/conftest.py` has an autouse `settings_env` fixture that sets the five required fields via `monkeypatch.setenv` and clears the `get_settings()` cache before and after each test. Individual tests can `monkeypatch.setenv`/`delenv` additional overrides — `test_config.py` does this to test the missing-secret and unknown-var failure paths.
