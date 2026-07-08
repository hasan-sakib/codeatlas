# Module 4: Database

## ERD

9 tables: `users`, `workspaces`, `repositories`, `indexing_jobs`, `files`, `chunks`, `conversations`, `messages`, `refresh_tokens`. FKs cascade on delete (`ON DELETE CASCADE`) all the way down: `workspaces → repositories → files → chunks`, and `users → conversations → messages`, `users → refresh_tokens`.

See `DESIGN.md` §14 for the full column-level DDL. Two deliberate additions beyond §14, made while implementing this module:

- **`conversations.turn_count`** and **`conversations.is_deleted`** — §14's DDL didn't include them, but Module 15 (Conversation Service)'s `ConversationRepositoryPort` design requires `increment_turn_count()` and `soft_delete()`. Added now rather than as an awkward later migration.
- Enum columns (`repositories.status`, `repositories.source_type`, `indexing_jobs.status`, `chunks.symbol_kind`, `chunks.chunk_type`, `messages.role`) use SQLAlchemy's `Enum(..., native_enum=False)` — renders as `VARCHAR` + `CHECK` constraint instead of a native Postgres `ENUM` type. Native Postgres enums require `ALTER TYPE ... ADD VALUE` outside a transaction to add a new value later, which is awkward with Alembic; `native_enum=False` avoids that entirely at the cost of a slightly less strict DB-level type.

## Layering

- `app/domain/entities/` — plain frozen dataclasses, zero SQLAlchemy dependency. Each entity file also owns its small enums (e.g. `RepositoryStatus` lives in `repository.py`, `MessageRole` in `message.py`) rather than a separate `value_objects/` package — kept simple since nothing yet needs to share an enum across multiple entities.
- `app/domain/ports/` — one `Protocol` per aggregate, typed purely in terms of domain entities.
- `app/infrastructure/db/models/` — SQLAlchemy `Mapped[...]` models, one file per table. `models/__init__.py` imports all of them so `Base.metadata` is fully populated for both Alembic autogenerate and `Base.metadata.create_all()` in tests.
- `app/infrastructure/db/repositories/` — one `SqlAlchemy{Aggregate}Repository` per port, each with a private `_to_entity()` mapper. ORM model instances never leak past a repository's own module.

## Session lifecycle

- **API (session-per-request):** `get_db_session()` (FastAPI dependency) commits on success, rolls back on exception, always closes.
- **Multi-repository atomic writes:** `UnitOfWork` wraps a session with explicit `.commit()`/`.rollback()` — unlike `get_db_session()`, it does **not** auto-commit on clean exit, only auto-rollback on exception. Callers must call `.commit()` themselves inside the `async with` block.
- **DI:** `app/core/di.py` exposes `provide_{aggregate}_repository(session: DbSession)` factories for every one of the 9 repositories, ready to use as `Depends(provide_chunk_repository)` in a route.

## `chunks.id` == Qdrant point id

`chunks.id` is generated in Python (`uuid4()` as the SQLAlchemy column default), not server-side — it must be known *before* the corresponding Qdrant upsert call in Module 10. Never regenerate a chunk's UUID on reindex without also updating the corresponding vector point.

## Real bugs found while building this (not just design-doc theory)

1. **Alembic's async env.py must not assume a working directory.** The generated `env.py` needs `app.core.config`/`app.infrastructure.db.base` importable regardless of where `alembic` is invoked from — same lesson as Module 2's `.env` path handling. Fixed by inserting the backend root onto `sys.path` at the top of `env.py`.
2. **`asyncpg` connections can't cross event loops.** The first integration-test conftest made the Postgres testcontainer's SQLAlchemy engine module-scoped (reused across tests). `pytest-asyncio` gives each test function its own event loop by default, and asyncpg's connection pool is bound to the loop it was created on — reusing it from a different test's loop raised `InterfaceError: cannot perform operation: another operation is in progress`. Fixed by making the engine function-scoped (fresh per test) while keeping the container itself module-scoped (container startup is the expensive part; engine creation is cheap, and `Base.metadata.create_all(checkfirst=True)` is a no-op on tables that already exist).
3. **`messages.created_at`'s `server_default=func.now()` was wrong, but nothing here tested it.** `conversations`/`messages` were built ahead of schedule in this module (see the `turn_count`/`is_deleted` note above) but this module's own testing scope never exercised `SqlAlchemyConversationRepository`/`SqlAlchemyMessageRepository` directly. Module 15 (Conversation Service), the first actual consumer, found via real Postgres integration tests that `now()` is transaction-scoped (returns the same value for every statement in one transaction), making multiple messages appended in one session indistinguishable by `created_at` — breaking `list_recent`'s chronological ordering. Fixed there (`func.clock_timestamp()` + migration `0002`); noted here as a reminder that "build the schema ahead of schedule" deliberately defers real test coverage to whichever module first depends on the behavior, not just the shape.

## Testing notes

- Unit tests mock the `AsyncSession` directly (`unittest.mock.AsyncMock`/`MagicMock`) — no real DB, verifying the ORM-instance-building and query-shape logic in isolation.
- Integration tests use `testcontainers.postgres.PostgresContainer`, actually running: the real `alembic upgrade head` migration (via subprocess, against a fresh container — proves the migration file itself works, not just the ORM models), FK cascade deletes, the `files(repository_id, path)` unique constraint, and a full chunk round-trip preserving `symbol_kind`/`imports`/`git_blame`/`embedding_version`.
- One correction to the design doc's own testing-plan text: it named the unique constraint under test as `files(repository_id, content_hash)`, but §14's actual DDL (and the real semantics — content hash detects *changes* to a given path, it isn't itself unique) defines the constraint as `files(repository_id, path)`. Tested the constraint that's actually in the schema.
- CI runs `alembic upgrade head` then `alembic check` against a real `postgres:16-alpine` service container on every push, failing the build if models and migrations drift.
