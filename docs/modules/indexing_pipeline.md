# Module 21: Indexing Pipeline

Not part of the original 20-module plan. Every prior module built a piece of the RAG stack (parsing, chunking, embedding, vector store, retrieval, chat) but no module was ever assigned to actually wire a real, Celery-backed job that clones a repository and drives those pieces end to end against real source code. `CreateRepositoryUseCase` (Module 6) persisted a `Repository` + `IndexingJob` row and called `IndexingTaskDispatcherPort.dispatch()` — but the only implementation was `NullIndexingTaskDispatcher`, which logged a warning and did nothing. `app/workers/` was an empty package; `worker`'s Compose command was `sleep infinity`. This module closes that gap.

## Scope

- `app/workers/celery_app.py` — the Celery application instance.
- `app/application/services/repository_walker.py` — `.gitignore`-aware, exclude/size-capped file walking.
- `app/application/use_cases/indexing/run_indexing_pipeline.py` — `RunIndexingPipelineUseCase`, the orchestrator.
- `app/workers/tasks/indexing_tasks.py` — the Celery task, a thin sync-to-async bridge into the use case.
- `app/infrastructure/queue/celery_indexing_task_dispatcher.py` — the real `IndexingTaskDispatcherPort`, replacing `NullIndexingTaskDispatcher`.
- `CelerySettings`/`IndexingSettings` in `app/core/config.py`.
- Two new endpoints on `app/api/routers/repositories.py`: `GET .../jobs` and `GET .../jobs/{job_id}`, so a caller can actually observe indexing progress — these didn't exist before this module, even though `IndexingJobRepository` and the SSE progress-bridge infrastructure (Module 16) did.
- `worker`'s real command + healthcheck in `infra/docker/docker-compose.yml`.

## The lazy-configuration pattern (and why it matters here specifically)

`celery_app.py` builds the bare `Celery("codeatlas")` instance at module scope but deliberately does **not** call `get_settings()` there. Settings-dependent module-level singletons across this codebase (`get_redis_client()`, `provide_qdrant_client()`) already follow this rule; Celery's app object is a third case with a sharper failure mode: `app/workers/tasks/indexing_tasks.py` needs the *bare* `celery_app` object at import time just to decorate `index_repository_task`, and test files transitively import that module before any pytest fixture (including autouse ones) has set required env vars. An eager `get_settings()` call at either module's top level breaks test collection outright with a `pydantic_core.ValidationError`, before a single test even runs — verified directly by moving the real `.env` aside and attempting a clean-room import.

The fix: `ensure_configured()` defers `get_settings()`, `configure_logging()`, and setting `celery_app.conf.broker_url`/`result_backend` into a function body, guarded by a module-level `_configured` flag so it only runs once per process. It's invoked two ways:

- Automatically via Celery's `worker_init` signal — fires only when a real `celery worker` process starts, never on bare import.
- Explicitly by `CeleryIndexingTaskDispatcher.dispatch()`, before every `send_task()` call from the API process (which never starts a worker, so `worker_init` never fires there).

## `RunIndexingPipelineUseCase`

Clone → walk → per file: detect language → parse+chunk (code) or semantic-chunk (markdown) → embed → persist → upsert. Processes one file at a time end to end, rather than four global phases (parse-all, then chunk-all, then embed-all, then upsert-all):

- **Bounded memory** — never holds every file's parsed AST or every chunk's embedding in memory at once, unlike a phase-per-stage design would for a large repository.
- **Fine-grained, real progress** — `IndexingJob.files_processed`/`files_total`/`chunks_total` update after every file, not only at phase boundaries.
- **Per-file failure isolation (FR-24)** — a single file's parse/chunk/embed/persist failure is caught, logged (`indexing.file_failed`), and skipped; the job continues and still reaches `COMPLETED`. Verified by a dedicated test where one file's embedding call raises and the other files still land correctly.

`IndexingJobStatus.PARSING` is used as the umbrella status for the entire per-file loop rather than the enum's separate `CHUNKING`/`EMBEDDING`/`UPSERTING` values — those describe global sequential phases this per-file design doesn't have. The job's own progress counters carry the real granularity instead.

### Ordering fix caught by testing, not review

The first version persisted the `File` row (with its new `content_hash`) *before* calling `embed_batch()`. A test simulating a transient embedding failure for one file caught the consequence directly: the file's row would still get updated to the new content hash even though nothing was actually embedded or upserted for it. Since the incremental-reindex skip (`existing.content_hash == content_hash → skip`) trusts that hash unconditionally, a transient embedding failure would have permanently blackholed that file — no future re-index would ever retry it, since the hash would already "match." Fixed by moving all persistence (`file_repo.upsert`, `chunk_repo.deactivate_by_file`, `chunk_repo.add_many`, `vector_store.upsert`) to *after* embedding succeeds, so a failure anywhere in a file's pipeline leaves that file's previous state — old hash, old chunks, old vectors — completely untouched.

### Two distinct "embedding_version" fields, deliberately not unified

- `Chunk.embedding_version: int | None` (Postgres) — a generation counter for a future re-embedding-migration workflow (`DESIGN.md` §15's alias-cutover scheme). That workflow doesn't exist yet and only one generation has ever existed, so this is a fixed `1`.
- `ChunkUpsertItem.embedding_version: str` (Qdrant payload) — must equal `settings.embedding.model_id` (e.g. `"bge-m3:v1"`), because retrieval's own filter construction (Module 11) filters Qdrant search results on this exact string. Passed into the use case's constructor from the caller (the Celery task, sourcing it from `get_settings().embedding.model_id`) rather than hardcoded, so it can never drift out of sync with what retrieval expects — a mismatch here wouldn't error, it would just make every indexed chunk invisible to every search.

### Metadata re-attachment across chunk merging

`MetadataExtractor.extract()` returns one `ChunkMetadataCandidate` per original *symbol*, but `ChunkMerger` (Module 8) can combine several adjacent small symbols into one merged `ChunkCandidate` whose line range doesn't exactly match any single original symbol.

- **Imports** are file-scoped — `MetadataExtractor`'s own contract is that every symbol in a file shares the same import list — so any one `ChunkMetadataCandidate.imports` is representative of the whole file, regardless of merging.
- **Git blame** is genuinely per-line-range. A merged chunk gets blame only on an exact `(start_line, end_line)` match against the original metadata; a chunk that doesn't match (because it was merged) simply carries no blame rather than a misleading partial one. Accepted as a minor, documented simplification — blame is supplementary citation metadata, not core retrieval correctness.

## The Celery task is a thin bridge, nothing more

```python
@celery_app.task(name="indexing.index_repository", bind=True, max_retries=0)
def index_repository_task(self, job_id: str) -> None:
    ensure_configured()
    asyncio.run(_run(UUID(job_id)))
```

`_run` opens one session via `db_session_context()` (session-per-task, the pattern Module 4 established for exactly this — a Celery worker process is long-lived across many discrete task executions, unlike one FastAPI request), wires `RunIndexingPipelineUseCase` through the same `app/core/di.py` provider functions the API process uses, and awaits `execute(job_id)`. `CeleryIndexingTaskDispatcher.dispatch()` enqueues by task **name** via `celery_app.send_task(...)` rather than importing the task function directly — the API process never needs `RunIndexingPipelineUseCase`'s transitive dependencies importable at all, matching Celery's own client/worker decoupling.

## Testing notes

- `RunIndexingPipelineUseCase` unit tests fake every I/O port (`GitPort`, `EmbeddingPort`, `VectorStorePort`, all four repositories) but run the *real* walker, parser, and chunker against real temporary files on disk — `FakeGitPort.clone()` just returns a caller-supplied local directory instead of actually cloning. Covers: full end-to-end indexing, incremental-reindex skip (identical content_hash → zero new chunks, zero deactivation), per-file failure isolation, and top-level clone failure marking both the job and repository `FAILED`.
- `repository_walker` unit tests cover `.gitignore` matching, directory-name pruning (verified it doesn't merely filter but never descends — a nested file under an excluded directory is never yielded), oversized-file skipping, symlink skipping, and POSIX-style nested relative paths.
- `celery_app`/`indexing_tasks` unit tests verify task registration under the `indexing` queue route and the sync-to-async bridge (via Celery's eager mode, with `_run` monkeypatched — real DB/embedding/git infra is out of scope for this test, already covered by the use-case's own tests).
- `CeleryIndexingTaskDispatcher` unit test verifies it calls `send_task("indexing.index_repository", args=[str(job_id)])` and returns the resulting task id.
- The existing repository-routes integration test (`test_repository_routes.py`, real Postgres/Redis via testcontainers) now exercises the *real* dispatcher, not a null one — this caught a real gap: the integration fixture never pointed `CELERY__BROKER_URL`/`CELERY__RESULT_BACKEND` at the test container's Redis, so `CreateRepositoryUseCase` would have tried to reach `localhost:6379/1` by default. Fixed in `tests/integration/api/conftest.py` alongside this module, following the same pattern already used there for `REDIS__URL`.
- New integration test (`test_indexing_job_status_is_pollable_and_repository_scoped`) covers the two new job-status endpoints, including the same cross-workspace 404 anti-enumeration behavior every other repository-scoped route already has.

## Known follow-ups, deliberately not bundled into this module

- `indexing_job_duration_seconds` (Module 20) has no live call site yet — defined for exactly this pipeline but not instrumented.
- The Redis pub/sub progress channel Module 16's SSE bridge already expects (`indexing:progress:{job_id}`) has no publisher yet. Job progress today is pollable via `GET .../jobs/{job_id}` (backed by real `IndexingJob` row updates after every file), which is sufficient for FR-23; a live push-progress publisher remains future work.
- `File.last_commit_sha` is left `None` — the per-file "last commit that touched this path" isn't computed (would need a `git log -1 -- path` call `GitPort` doesn't expose today), to avoid setting a field to an approximated-but-wrong value.
