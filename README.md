# CodeAtlas

An AI Software Engineering Copilot that helps developers understand large codebases, answer questions about repositories, generate documentation, explain architecture, search semantically across code, and assist with debugging — powered by Retrieval-Augmented Generation (RAG).

See [docs/design/DESIGN.md](docs/design/DESIGN.md) for the full architecture and module-by-module implementation plan.

## Prerequisites

- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python package manager)

## Local dev quickstart

```bash
./scripts/bootstrap.sh                                  # copies .env.example -> .env, installs deps + git hooks
docker compose -f infra/docker/docker-compose.yml up     # starts api, worker, postgres, redis, qdrant, ollama
curl http://localhost:8000/health                        # {"status": "ok", "version": "0.1.0"}
```

Or run the API directly on the host:

```bash
cd backend
uv sync --all-groups
uv run uvicorn app.main:create_app --factory --reload
```

## Tests and linting

```bash
cd backend
uv run pytest tests -m "not integration"   # unit tests
uv run mypy app                            # type-check
uv run pre-commit run --all-files          # ruff + black + mypy + hygiene hooks
```

## Directory layout

Each top-level folder maps to a layer in the backend's Clean Architecture, or to a project-wide concern:

| Path | Purpose |
|---|---|
| `backend/app/domain/` | Entities, value objects, port interfaces — zero framework dependencies |
| `backend/app/application/` | Use cases / services / DTOs — depends only on `domain` |
| `backend/app/infrastructure/` | Adapters (DB, vector store, LLM, parsing, chunking, cache, storage, queue) implementing `domain` ports |
| `backend/app/agent/` | LangGraph state graph, nodes, tools |
| `backend/app/api/` | FastAPI routers, schemas, middleware, SSE streaming |
| `backend/app/workers/` | Celery worker entrypoint + tasks |
| `backend/tests/` | `unit/`, `integration/`, `e2e/` — mirrors `app/` |
| `frontend/` | Next.js App Router frontend |
| `docs/` | MkDocs site, including the full design document |
| `infra/docker/` | Dockerfiles and Compose files |
| `scripts/` | Dev convenience scripts |

## Documentation

Full docs are built with MkDocs from the `docs/` directory — see [docs/index.md](docs/index.md).
