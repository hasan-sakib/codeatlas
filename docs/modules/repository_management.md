# Module 6: Repository Management

## Scope vs. Module 4

Module 4 already built the `Workspace`/`Repository`/`IndexingJob` domain entities, their ports, and full SQLAlchemy models/repositories. Module 6 adds only what Module 4 didn't: application use cases (workspace CRUD, repository registration/list/get/delete), a `GitPort` + SSRF-hardened `GitPythonAdapter`, API routers/schemas, and the supporting domain exceptions/value objects/DI wiring.

## Layering

- `app/application/use_cases/workspaces/` — `CreateWorkspaceUseCase` (auto-slugifies the name; no slug field in the API), `ListWorkspacesUseCase`, `GetWorkspaceUseCase`.
- `app/application/use_cases/indexing/` — `CreateRepositoryUseCase`, `ListRepositoriesUseCase`, `GetRepositoryUseCase`, `DeleteRepositoryUseCase`.
- `app/domain/ports/git_port.py`, `indexing_task_dispatcher.py` — new ports.
- `app/infrastructure/vcs/` — `url_validator.py` (SSRF checks), `git_python_adapter.py` (`GitPort` implementation).
- `app/infrastructure/queue/null_indexing_task_dispatcher.py` — placeholder adapter (see below).
- `app/api/routers/workspaces.py`, `repositories.py` — the latter nested under `/api/v1/workspaces/{workspace_id}/repositories`, reusing `require_workspace_access` from Module 5.

## Three deliberate architecture decisions

1. **`require_workspace_access` (Module 5) now delegates to `GetWorkspaceUseCase`.** The "does this workspace exist and is it mine" rule now lives in exactly one place in the application layer instead of inline in a FastAPI dependency. `require_workspace_access` is a thin translation of `WorkspaceNotFoundError` → `HTTPException(404)`. Same anti-enumeration behavior as before (404 for both "doesn't exist" and "not yours"), just relocated.

2. **SSRF defense is split by cost, not duplicated — and this is a security-correctness decision, not just a layering convenience.**
   - `CreateRepositoryUseCase` calls only `validate_repository_url()` — a cheap, synchronous, no-I/O scheme/format check (rejects `file://`, `ftp://`, embedded passwords, embedded https usernames, non-default ports). This runs at registration time so obviously-bad input fails fast with a clear `400`.
   - The authoritative check — DNS resolution, private/loopback/link-local/reserved/multicast IP rejection (this covers the `169.254.169.254` cloud metadata address), and a post-redirect re-check — happens exactly once, immediately before the real clone, inside `GitPythonAdapter.clone()`.
   - Checking IPs at registration time and trusting that result later would itself be a TOCTOU bug: DNS can change between registering a repository and actually cloning it, which may happen much later (queued, retried, etc.). Doing the authoritative check only at the point of actual connection is strictly more correct, not just cheaper.
   - `GitPythonAdapter.clone()` checks the original host, then (for `https` only — `ssh` has no redirect concept) follows redirects via `httpx.AsyncClient(follow_redirects=True)` and re-checks the *final* resolved host only if it differs from the original, avoiding a redundant duplicate DNS lookup on the common non-redirected path.
   - Only explicit `scheme://host/...` URLs are accepted — scp-like syntax (`git@host:org/repo.git`) is rejected because it can't be reliably parsed for a hostname to validate.

3. **Two forward-references to not-yet-built modules are deferred, not faked:**
   - `IndexingTaskDispatcherPort` has a `NullIndexingTaskDispatcher` stub adapter. It persists nothing and enqueues nothing — it exists only so `CreateRepositoryUseCase` has something to call today. Every call logs a `warning`-level structured log (`indexing_task_dispatch.not_implemented`) so this is never mistaken for a working queue integration. Verified in the live smoke test that the warning actually appears with the job id and correlation id attached. Replace with a real Celery-backed adapter once the indexing pipeline exists.
   - `DeleteRepositoryUseCase` does **not** reference a `VectorStorePort` — that port belongs to Module 10, which doesn't exist yet. Deletion only cascades the Postgres rows (`files`/`chunks`/`indexing_jobs` via the FK `ON DELETE CASCADE` from Module 4) for now. Revisit this use case in Module 10 to add `vector_store.delete_by_filter(workspace_id=..., repository_id=...)` after the row delete succeeds.

## Other notable decisions

- **Workspace slugs are auto-generated, never user-supplied** — `_slugify()` in `create_workspace.py` lowercases, replaces non-alphanumerics with hyphens, and falls back to `"workspace"` for a name that slugifies to nothing. Uniqueness is checked via `list_for_owner()` before insert; this has a small accepted race window (two concurrent requests for the same owner+name could both pass the check) backstopped by the DB's `uq_workspaces_owner_slug` constraint. Accepted for v1 as low-severity and self-correctable by retry — unlike the refresh-token rotation race (Module 5), which needed an atomic guarantee because it's a security boundary.
- **Tenant isolation for repositories is enforced in the use case, not just the router.** `GetRepositoryUseCase`/`DeleteRepositoryUseCase` treat a repository that exists but belongs to a *different* workspace as not found (same anti-enumeration rationale as workspaces) — verified by an integration test creating two workspaces for the same owner and confirming a cross-workspace lookup 404s.
- **`CreateRepositoryUseCase.requested_by`** isn't persisted anywhere (no `created_by` column on `repositories` yet) but is used in a structured audit log line (`repository.registered`) — kept in the signature per the design's own interface rather than dropped, given it into real use immediately rather than left as a dead parameter.

## Testing notes

- Unit tests for `url_validator.py` mock `socket.getaddrinfo` — no real DNS/network — covering scheme rejection, embedded credentials, unexpected ports, and IP-range rejection (private, loopback, link-local/cloud-metadata, IPv6 loopback).
- Unit tests for `GitPythonAdapter` mock `_clone_sync`, `git.Repo`, `httpx.AsyncClient`, and `asyncio.create_subprocess_exec` — no real git/network operations. The redirect-rejection test is the key regression: given a mocked HTTP client claiming a redirect to a disallowed host, `clone()` raises and `_clone_sync` is never called. Also covers the size-limit and clone-timeout cleanup paths (`shutil.rmtree` on failure) and `get_blame`'s line-porcelain parser.
- Integration tests (`tests/integration/api/test_workspace_routes.py`, `test_repository_routes.py`, real Postgres + Redis via `testcontainers`) cover the full create/list/get/delete flow, duplicate-name `409`, unauthenticated `401`/`403`, non-owner `404`, disallowed-URL `400`, and the cross-workspace tenant-isolation `404`.
- Live smoke test (manual): booted `create_app()` against throwaway `postgres:16`/`redis:7` containers with a real `alembic upgrade head`, then curled the full workspace+repository flow — every status code matched, and the placeholder dispatcher's warning log was confirmed present with the correct `job_id`/`correlation_id`.
- `pytest -q` (unit): 95 passed. `pytest -m integration`: 17 passed. `mypy app`: no issues, 102 source files. `ruff check` / `black --check`: clean. `pre-commit run --all-files`: clean.
