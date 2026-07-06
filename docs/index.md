# CodeAtlas

An AI Software Engineering Copilot that helps developers understand large codebases, answer questions about repositories, generate documentation, explain architecture, search semantically across code, and assist with debugging — powered by Retrieval-Augmented Generation (RAG).

## Where to start

- [Design Document](design/DESIGN.md) — the full Phase 1 architecture: requirements, high/low-level design, database and vector store schema, API design, RAG/retrieval/agent pipelines, deployment, security, and the 20-module implementation plan.

## Module documentation

Each module (see the Design Document's "Module Planning" section) gets its own page here as it's implemented:

- Module 1: Project Initialization — this scaffold.
- [Module 2: Configuration System](modules/config.md) — settings hierarchy, `.env` loading, fail-fast validation.
- [Module 3: Logging](modules/logging.md) — structlog processor chain, correlation IDs, redaction, Celery signal hook.
- [Module 4: Database](modules/database.md) — domain entities/ports, SQLAlchemy models & repositories for all 9 tables, Alembic migrations, unit of work.
- [Module 5: Authentication](modules/auth.md) — JWT access tokens, rotating opaque refresh tokens, Redis-backed access-token blacklist, and a Postgres row-lock fix for a genuine refresh-token-rotation race condition.
- [Module 6: Repository Management](modules/repository_management.md) — workspace/repository registration use cases and an SSRF-hardened Git cloning adapter, with the authoritative IP-allowlist check deferred to clone time (not registration time) to avoid a TOCTOU gap.
- [Module 7: Parser Engine](modules/parser_engine.md) — a plugin-registered tree-sitter parser for Python/JS/TS with symbol/import extraction, verified empirically against the actual installed tree-sitter API rather than assumed.

More pages are added as subsequent modules land.
