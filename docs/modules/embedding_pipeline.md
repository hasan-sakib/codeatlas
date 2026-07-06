# Module 9: Embedding Pipeline

## Purpose

The single `EmbeddingPort` implementation, backed by BGE-M3, producing both dense and sparse vectors with a Redis cache — used identically by the (future) bulk indexing pipeline and single-query retrieval, so retrieval never sees embedding behavior diverge from what was indexed.

## Why FlagEmbedding, not a lighter library

BGE-M3's *sparse* (lexical-weight) output comes from a dedicated linear head (`sparse_linear.pt` in the model repo) that's specific to the FlagEmbedding wrapper — a generic `sentence-transformers`/`transformers` load only gets the dense embeddings. Since Qdrant's collection (Module 10) is designed around named `dense` + `sparse` vectors for hybrid search, FlagEmbedding is the only practical way to get both from one model call, matching DESIGN.md's explicit choice. The trade-off, accepted deliberately: `FlagEmbedding` pulls in `torch`, `transformers`, `datasets`, `accelerate`, `sentence-transformers`, `peft`, and `ir-datasets` as base dependencies (not just extras) — real weight for a backend service, but not something a lighter alternative avoids without dropping the sparse vectors.

## Layering

- `app/domain/value_objects/embedding_result.py` — `EmbeddingResult` (`dense: list[float]`, `sparse: dict[int, float]`, `model_id: str`).
- `app/domain/ports/embedding_port.py` — `EmbeddingPort` Protocol (`embed_batch`, `embed_query`).
- `app/infrastructure/embeddings/text_normalizer.py` — `normalize_for_cache_key()`.
- `app/infrastructure/embeddings/embedding_cache.py` — `EmbeddingCachePort` + `RedisEmbeddingCache`.
- `app/infrastructure/embeddings/bge_m3_adapter.py` — `BgeM3Adapter`, the `EmbeddingPort` implementation.
- `app/core/config.py` — `EmbeddingSettings` (`model_name_or_path`, `model_id`, `batch_size`, `use_fp16`, `cache_ttl_seconds`).
- `app/core/di.py` — `provide_embedding_port()`, an `lru_cache`d singleton (the model is loaded once per process into the adapter's own instance state — a fresh instance per request would reload a multi-hundred-MB model on every call).

## Cache key formula and the embedding_version implication

`normalize_for_cache_key(text, model_id)` = `sha256(f"{model_id}:{strip_and_collapse_whitespace(text)}")`. Folding `model_id` into the hash means it doubles as the embedding-version namespace: `EmbeddingSettings.model_id` (e.g. `"bge-m3:v1"`) is a separate config value from `model_name_or_path` (the actual `BAAI/bge-m3` HF repo). Bumping `model_id` to `"bge-m3:v2"` after a re-embedding migration makes every old cache key permanently unreachable — no explicit flush needed, and it can't accidentally collide with pre-migration entries.

## The two call paths are one code path

`embed_query()` is `embed_batch([text])`, not a separate implementation. `embed_batch` never waits to accumulate a larger batch across calls — each call processes exactly what it's given, immediately — so a single-item call already *is* "skip batching, embed now." Design called for treating these as parallel paths sharing logic; on inspection, `embed_query` had literally nothing left to do differently once that's true, so implementing it as a one-line delegation avoided duplicating the whole cache-then-model flow for no behavioral difference.

## Two decisions that avoided regressing the rest of the test suite

1. **`warm_up()` is implemented and unit-tested, but deliberately not wired into `main.py`'s startup lifespan yet.** No endpoint currently calls `embed_query`/`embed_batch` — retrieval/chat don't exist until later modules — so wiring warm-up into the FastAPI lifespan now would make *every* existing integration test that boots the app via `TestClient(create_app())` (auth, workspace, repository routes — none of which touch embeddings) pay a real ~10-second BGE-M3 model load on every test run, for a capability nothing yet exercises. Wire `provide_embedding_port().warm_up()` into the lifespan when Module 11 (Retriever) or the chat endpoint that actually calls `embed_query` lands — that's the point where the app genuinely needs to be ready to serve embedding requests immediately. Same reasoning applies to the Celery `worker_process_init` hook once a worker process exists.
2. **The checked-in test suite never downloads or loads the real model.** BGE-M3's weights are a ~2.1GB download — verified directly (`content-length: 2271145830` via HTTP HEAD on the LFS-resolved URL) — that would make every future `pytest` run (and every fresh CI checkout, and every other contributor's first test run) pay a multi-minute one-time tax unrelated to whatever they're actually changing. Design's own testing plan explicitly allows for this ("model mocked... otherwise mocked at the model boundary but real Redis"). Unit tests patch `BgeM3Adapter._load_model` and the module-level `_encode_sync` function; the integration test uses real Redis (testcontainers) with the same stubbed model boundary, proving the actual cache serialization/orchestration against a real Redis instance without the network dependency.

## Real-model verification (done by hand, not part of the automated suite)

Downloaded and ran the actual `BAAI/bge-m3` model once during development to verify the design's assumptions rather than guess from documentation:
- `BGEM3FlagModel.encode(texts, return_dense=True, return_sparse=True)` returns `{"dense_vecs": ndarray(N, 1024) float32, "lexical_weights": list[dict[str, float32]], ...}`.
- **`lexical_weights` keys are strings** (e.g. `"33600"`), not native ints — despite `EmbeddingResult.sparse` being typed `dict[int, float]`. `_encode_sync` converts (`int(token_id)`) on the way in.
- `use_fp16=True` (the shipped default) runs correctly on CPU-only hardware — didn't silently require a GPU.
- Full `BgeM3Adapter` flow verified end-to-end with a fake cache: `warm_up()` ~9.9s (cold model load + one inference), a 3-item `embed_batch` with one duplicate text correctly deduplicated to one Redis write, `embed_query` correctly served from the batch call's cache entry.
- `_encode_sync` raises `ValueError` if the model ever returns a non-1024-dim dense vector (a real defensive check at the ML-model boundary — verified via a stubbed wrong-shape model in `test_encode_sync_raises_on_wrong_dense_dimension`).

## A second real finding: `tokenizers` lost its `py.typed` marker at the version `transformers` pins

Module 8 used `tokenizers>=0.23` directly, which ships a `py.typed` marker and typed `.pyi` stubs — confirmed clean under mypy. Installing `FlagEmbedding` here forced `tokenizers` down to `0.22.2` (via `transformers`'s own version constraint), and — verified directly by listing the installed package's files — `0.22.2` does **not** ship `py.typed`. Added `ignore_missing_imports` overrides for `FlagEmbedding.*` and `tokenizers.*` in `pyproject.toml`, matching the existing `celery.*` precedent, rather than fighting the dependency resolver over a two-minor-version difference that has no functional impact here.

## Testing notes

- `test_text_normalizer.py`: whitespace-insensitivity, per-`model_id` isolation, valid hex digest.
- `test_bge_m3_adapter.py`: all-hit (model never called), all-miss (model called once per `batch_size`-sized chunk, one `set_many` call for everything), mixed hit/miss preserves input order, batch-size chunking of a 250-item list (`[32]*7 + [26]`), `embed_query`/`warm_up` delegate correctly, and the dense-dimension shape-contract regression.
- `test_embedding_cache.py` (integration, real Redis via testcontainers): empty-cache miss, full round-trip fidelity (including `int` sparse keys surviving JSON), TTL applied correctly.
- `test_bge_m3_adapter_integration.py` (integration, real Redis + stubbed model): proves cache hit-rate improves across overlapping `embed_batch` calls against a real Redis instance.
- `pytest -q`: 171 passed (16 new). `mypy app`: no issues, 129 source files. `ruff`/`black`: clean. `pre-commit run --all-files`: clean. Full suite still runs in ~11s — no test in the checked-in suite loads the real model.
- App boot confirmed still fast and side-effect-free for embeddings (no eager model load at import or startup time) — `provide_embedding_port()` only loads the model on first real `embed_batch`/`embed_query`/`warm_up()` call.
