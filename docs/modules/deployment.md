# Module 19: Deployment

## Purpose

Package the API, worker, and frontend into reproducible Docker images and wire up dev/prod Compose topologies — the last piece needed to run the whole stack with one command instead of the ad hoc `docker run` + native `uvicorn`/`npm run dev` juggling used to verify every earlier module. This module's own empirical verification (actually building every image and bringing up the full stack, not just authoring YAML) surfaced five real, previously-invisible bugs, documented below in the order they were found.

## What already existed vs. what this module built

Module 1 had already created `backend/Dockerfile` (multi-stage, non-root user) and a base `infra/docker/docker-compose.yml` with `backend-api`/`worker`/`postgres`/`redis`/`qdrant`/`ollama` — deliberately with no host ports, bind mounts, or a `frontend` service, and a comment explicitly deferring the dev/prod split to this module. This module: split the single `codeatlas_net` into `frontend_net`/`backend_net` (matching DESIGN.md §22's network diagram) with per-service assignment; added the `frontend` service (didn't exist at all — Module 18 built the Next.js app but never its container); wrote `docker-compose.dev.yml` and `docker-compose.prod.yml`; wrote `frontend/Dockerfile`; and hardened `backend/Dockerfile`.

## Bug 1: `DATABASE__URL`/`QDRANT__URL`/`REDIS__URL`/`OLLAMA__BASE_URL` point at `localhost`, which is wrong for a containerized backend-api

The root `.env.example` (Module 2) uses `localhost` for these four — correct for running `backend-api` natively against Dockerized infra with published ports (the workflow used to verify every prior module), but `localhost` inside a `backend-api` *container* resolves to the container itself, not to sibling containers. Fixed by having `infra/docker/docker-compose.yml` override just these four keys via `environment:` (which always wins over `env_file:`) to the Compose service DNS names — `.env` keeps holding real secrets/tunables, these four stay a topology fact owned by Compose.

## Bug 2: `git` binary missing from the runtime image

`GitPythonAdapter` (Module 6) imports `git` (GitPython), which validates a real `git` executable **at import time**, not just at clone time. `python:3.12-slim` has no `git` installed, so `backend-api` crashed on startup with `ImportError: Bad git executable` — caught immediately by the container's own healthcheck failing, not by any prior test (no test suite run had ever actually started the container from a cold, non-dev image). Fixed with `apt-get install -y --no-install-recommends git` in the runtime stage.

## Bug 3: `alembic.ini`/`alembic/` never copied into the image

The Dockerfile only ever copied `app/`, so `docker compose exec backend-api alembic upgrade head` failed with `No 'script_location' key found`. Every prior migration run in this project happened via `uv run alembic` on the host — nobody had run migrations from inside a built container until this module did. Fixed by copying both into the runtime stage.

## Bug 4 (the big one): `EMBEDDING__USE_FP16=true` silently produces all-NaN embeddings on CPU

`/search` returned a 500 the first time it was exercised against a fully-containerized `backend-api`: `Qdrant: Format error in JSON body: Expected some form of vector, id, or a type of query`. Root-caused by directly calling `provide_embedding_port().embed_query(...)` inside the container and inspecting the result: **all 1024 dense values were NaN**, and the sparse vector was empty. `BgeM3Adapter._load_model` passed `use_fp16=True` (the config default, per Module 9) straight through to `BGEM3FlagModel` regardless of hardware — half-precision matmul on CPU is unreliable (many CPU BLAS kernels don't properly support it) and silently produced garbage instead of raising. The exact same setting is harmless on a host with a CUDA GPU; it corrupted every embedding in this CPU-only container with no exception anywhere in the call chain — Qdrant's JSON parser was the only thing that ever complained, and only because `NaN` isn't valid JSON.

Fixed at the source (`app/infrastructure/embeddings/bge_m3_adapter.py`), not by changing the config default: `_load_model` now gates `use_fp16` on `torch.cuda.is_available()`, logging a warning when the configured value gets overridden. This protects every deployment regardless of what `.env` says, rather than relying on everyone remembering to set `EMBEDDING__USE_FP16=false` for CPU. Regression-tested in `tests/unit/infrastructure/embeddings/test_bge_m3_adapter_fp16_gating.py` (separate file from the existing adapter tests, which stub out `_load_model` entirely via an autouse fixture and so can't exercise this logic).

## Bug 5: no persistent volume for the HuggingFace model cache

Every container recreation re-downloaded BGE-M3's multi-GB weights from scratch — verified directly (a fresh container took ~7 minutes on first embedding call, all of it `Fetching 30 files`). Fixed with a new named volume (`model_cache`) mounted at `$HF_HOME=/data/hf-cache`, shared by `backend-api` and `worker`. Verified the fix directly: after warm-up, `du -sh /data/hf-cache` showed 512MB cached, and a full container **restart** (not just `docker compose up`) loaded the model in seconds with no re-download.

## A related finding: startup warm-up was never wired up, and prod's memory limit was wrong

Loading BGE-M3 from the now-cached volume still took several minutes on first use in this environment (disk I/O, not network) — this project's `BgeM3Adapter.warm_up()` (Module 9) was built for exactly this reason but was never called anywhere. Wired it into a new FastAPI `lifespan` in `app/main.py`, so the model loads *before* the container accepts traffic — the existing healthcheck (`depends_on: condition: service_healthy`) is what now makes a slow cold start visible, instead of the first real user silently waiting minutes for what looks like a hung request.

This is gated on `settings.environment == "test"` (skipped in that case) because `tests/integration/api/conftest.py`'s `api_client` fixture is the *only* place in the whole suite that uses `with TestClient(create_app()) as client:` — the context-manager form is what actually triggers ASGI lifespan events (a plain `TestClient(create_app())`, used elsewhere, does not) — and without the gate, every test using that fixture would load the real model. `EmbeddingPort`'s Protocol gained an explicit `warm_up()` method (previously only on the concrete `BgeM3Adapter`) since the lifespan calls it through the DI-provided interface, not the concrete class.

Bringing up the **prod** overlay with this fix active then OOM-killed `backend-api` (`docker inspect` confirmed `OOMKilled: true`) — the fp16→fp32 correctness fix from Bug 4 roughly doubles BGE-M3's memory footprint, and the prod overlay's original 2GB limit (set before any of this was known) no longer fit. Raised to 4GB for both `backend-api` and `worker`; re-verified with `docker stats` showing steady-state usage around 1.7GB, comfortable headroom under the new limit.

## Design decisions

- **One shared `backend/Dockerfile` for `backend-api` and `worker`**, not the original design doc's `Dockerfile.api`/`Dockerfile.worker` split — `worker` currently only overrides `command:` (it's still a placeholder; the Celery app doesn't exist yet), so two near-identical Dockerfiles would add nothing. Revisit if the two services' dependencies ever diverge.
- **`docker-compose.prod.yml` still uses `build:`, not a pinned `image:`** — the design's target model (CI publishes tagged images, prod pulls them) requires a registry/CI pipeline that doesn't exist yet (explicitly out of scope — see the CI gaps below). Using `build:` keeps this overlay actually runnable and testable today; swap to `image: ghcr.io/.../codeatlas-backend:${TAG}` once that pipeline exists.
- **The frontend's `SESSION_SECRET` lives in its own `frontend/.env`, not the shared root `.env`.** Discovered the hard way: the backend's `Settings` model has `extra="forbid"` (a deliberate typo guard, Module 2) and *also* falls back to reading `../.env` from the backend's own working directory — so putting a frontend-only key in the shared file broke `Settings()` construction, and with it every backend test, the instant a populated root `.env` existed. The `frontend` service's Compose definition points its `env_file` at `../../frontend/.env` instead.
- **`codeatlas_storage` stays declared but unattached** — reserved for the indexing pipeline's cloned-repository storage (`StoragePort`, per DESIGN.md §13), which doesn't exist yet (no storage module, no configurable storage root in `app/core/config.py`). Mounting it to a made-up path now would be fabricating scope for an unbuilt module.
- **Third-party image tags (`qdrant/qdrant:latest`, `ollama/ollama:latest`) were left as Module 1 set them**, not repinned to a specific version, despite DESIGN.md §29's "never `:latest`" rule technically applying to them too — that rule is stated in the context of this project's *own* built images (git-SHA/semver tags for reproducible rollback), and repinning vendor base images is a larger, separate hardening pass better done deliberately (with an explicit compatibility-tested version choice) than as a drive-by edit here. Flagged as a known follow-up, not silently left broken: a version skew between the `:latest` Qdrant server and the pinned `qdrant-client` Python library is a real, demonstrated risk category (see Bug 4's investigation, where a version-skew theory was tested and ruled out for that specific bug, but the underlying exposure remains).

## Testing notes

- `docker build` on both `backend/Dockerfile` and `frontend/Dockerfile` standalone: both succeed.
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml config` / `-f docker-compose.prod.yml config`: both merge cleanly.
- `scripts/check_prod_topology.sh` (new): asserts via `docker compose config --format json` that only `frontend`/`backend-api` publish host ports and `backend_net` is `internal: true` — passes.
- **Full dev-overlay stack brought up for real** (`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`): all 7 services healthy; migrations run via `docker compose exec backend-api alembic upgrade head`; Qdrant collection bootstrapped the same way; a real Ollama model (`qwen3:4b`) pulled into the containerized `ollama` service; the full Playwright e2e suite (`npm run e2e`) passed against the entirely containerized stack — real Postgres, Redis, Qdrant, Ollama, backend-api, and frontend, all resolving each other by Docker service name, zero browser console errors.
- **Full prod-overlay stack also brought up for real**: confirmed via `docker inspect` that resource limits, restart policy, and log rotation all actually apply under plain `docker compose up` (not just `docker stack deploy` — a common Compose `deploy:` misconception, checked rather than assumed); confirmed `postgres`/`redis`/`qdrant`/`ollama` have no host port bindings while `backend-api`/`frontend` do; Playwright e2e suite passed against this stack too, after the memory-limit fix.
- `backend/tests/unit/infrastructure/embeddings/test_bge_m3_adapter_fp16_gating.py` (new, 3 tests): fp16 honored when CUDA is available; force-disabled without CUDA even if configured on; stays disabled without CUDA when configured off.
- Full backend suite after all fixes: `382 passed`. `mypy app`: clean (189 files; `EmbeddingPort` Protocol gained `warm_up()`, and the one existing fake implementing it was updated to match). `ruff`/`black`/`pre-commit run --all-files`: clean.
- Frontend: `tsc --noEmit`, `eslint`, and `npm test` (25 tests) all still clean — Module 19 touched no frontend application code, only its Dockerfile/`.dockerignore`/`.gitignore`.
- One pre-existing test (`test_send_message_streams_sse_response_and_persists_both_turns`, Module 17) flaked twice during this module's verification — traced to real resource contention between this module's own concurrent Docker containers and the native Ollama process they were competing with for CPU/RAM, not a regression: it passes in isolation, and the full suite ran clean (382/382) once all of this module's containers were torn down.
- Found and fixed a real, unrelated repo hygiene gap along the way: `frontend/test-results/` (Playwright's own output directory) had no `.gitignore` entry and was already tracked in git. Added `/test-results`, `/playwright-report`, `/blob-report`, `/playwright/.cache` to `frontend/.gitignore` and untracked the accidentally-committed file.

## Known gaps (explicitly not fixed here — out of this module's scope)

- No CI job builds or publishes these images yet (`.github/workflows/ci.yml` only lints/tests the backend; there's no frontend CI job at all). `docker-compose.prod.yml`'s `build:`-not-`image:` choice above is downstream of this gap.
- Third-party image version pinning (`qdrant/qdrant`, `ollama/ollama`) — see the design decision above.
- No reverse proxy / TLS termination in front of `frontend`/`backend-api` — both are directly published, matching DESIGN.md §22's own explicit "Phase 1" carve-out.
