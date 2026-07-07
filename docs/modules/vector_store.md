# Module 10: Vector Store

## Purpose

Own all Qdrant interaction behind `VectorStorePort`, centrally enforcing multi-tenant `workspace_id` isolation on every query, with a `code_chunks_v{n}` / `code_chunks_active` collection-alias versioning scheme so a future re-embedding migration needs zero downtime.

## Layering

- `app/domain/value_objects/chunk_upsert_item.py` — `ChunkUpsertItem` (deliberately excludes chunk text — Qdrant payload stays lean; text of record lives in Postgres).
- `app/domain/value_objects/search_result.py` — `SearchResult` (`chunk_id`, `score`).
- `app/domain/ports/vector_store_port.py` — `VectorStorePort` Protocol.
- `app/infrastructure/vectorstore/filters.py` — `build_tenant_filter()`, the **one and only** place a `Filter` touching `workspace_id` is constructed.
- `app/infrastructure/vectorstore/collection_schema.py` — vector/payload-index config, `create_versioned_collection`, `point_alias_to`, `list_collection_versions`.
- `app/infrastructure/vectorstore/qdrant_vector_store.py` — `QdrantVectorStore`, the `VectorStorePort` implementation.
- `app/core/di.py` — `provide_vector_store()`, an `lru_cache`d singleton (the underlying `AsyncQdrantClient` is a persistent connection, expensive to recreate per request — same rationale as the Redis client).

## The tenant-isolation guarantee is structural, not conventional

Every method on `VectorStorePort` takes `workspace_id` as a mandatory keyword-only parameter — there is no overload or default that omits it. Every one of `QdrantVectorStore`'s query-issuing methods routes through the single `build_tenant_filter()` function to construct its `Filter`/`FilterSelector`; no other code path constructs a `workspace_id`-touching filter anywhere in this module. `upsert()` goes one step further: it validates that every `ChunkUpsertItem.workspace_id` in the batch matches the `workspace_id` keyword argument, raising `ValueError` on any mismatch rather than silently trusting the caller — a batch can never accidentally write cross-tenant data even if a caller assembles it incorrectly.

## A real, load-bearing API discovery: `.search()` doesn't exist anymore

The design's own pseudocode assumed `client.search(collection_name=..., query_vector=NamedVector(name="dense", vector=...), ...)`. Verified directly against the installed `qdrant-client` (1.18.0) before writing any adapter code: **`AsyncQdrantClient.search` has been removed**, replaced by `.query_points(collection_name, query, using, query_filter, limit, ...)` — a single unified method for both dense and sparse named-vector search, where `query` accepts a raw `list[float]` (dense) or a `models.SparseVector` (sparse) and `using` selects which named vector to search against. Writing the adapter from the design doc's pseudocode without checking this would have shipped code that fails at the first real call. Confirmed empirically end-to-end (collection creation, alias creation, payload indexing, dense search, sparse search, tenant-filtered exclusion, delete) against a live `qdrant/qdrant:v1.18.2` container before writing any test.

## Alias bootstrap and cutover share one implementation

Verified directly: Qdrant's `update_collection_aliases` treats deleting a not-yet-existing alias as a no-op within the same atomic batch — it doesn't error. That means `point_alias_to()` doesn't need a separate "first-time bootstrap" code path versus a "later cutover" path; the same delete-then-create atomic operation pair handles both, and there is never a window where the alias is observably missing.

## Test container version pinning

`testcontainers.qdrant.QdrantContainer`'s default image is `qdrant/qdrant:v1.13.5`, which throws a client/server compatibility warning against `qdrant-client` 1.18.0 (major versions must match, minor must not differ by more than 1). The integration test fixture pins `qdrant/qdrant:v1.18.2` instead — verified this eliminates the warning entirely — so test output stays clean and the tested behavior matches what a correctly-configured production deployment would actually run.

## Testing notes

- `test_filters.py`: every parameter combination (bare, `+repository_id`, `+file_id`, `+extra`) still includes the `workspace_id` condition — the core regression protecting the "structurally enforced" claim.
- `test_collection_schema.py` (mocked `AsyncQdrantClient`): vector config matches `EMBEDDING_DIM`/`Distance.COSINE`; `create_versioned_collection` creates the collection then indexes every expected payload field; `point_alias_to` issues exactly one `update_collection_aliases` call containing both a `DeleteAliasOperation` and `CreateAliasOperation` — never two separate calls.
- `test_qdrant_vector_store.py` (mocked client): `upsert` builds `PointStruct.id` as `str(chunk_id)` with full payload, raises and never calls the client on a workspace mismatch; `search_dense`/`search_sparse` always pass a `query_filter` containing the tenant condition for every parameter combination tested; `delete_by_filter` scopes correctly.
- `test_qdrant_vector_store_integration.py` (real Qdrant via testcontainers): round-trip upsert+search for both dense and sparse; **the core multi-tenancy regression** — two workspaces upsert points with the same-shaped payload and an identical query vector, and a search scoped to workspace A never returns workspace B's point; `delete_by_filter` removes only the matching repository within a workspace, leaving siblings untouched; a real alias cutover to a fresh v2 collection correctly returns empty (the old point was never copied), proving the alias genuinely moved.
- `pytest -q`: 194 passed (23 new). `mypy app`: no issues, 136 source files. `ruff`/`black`: clean. `pre-commit run --all-files`: clean.
- No live-server test — this module has no HTTP surface yet (consumed by the future indexing pipeline and retrieval use cases). Verified instead by running the full adapter against a real Qdrant container during development (collection/alias bootstrap, upsert, dense/sparse search, mismatched-workspace rejection, delete) before any test was written, and confirmed the app still boots cleanly with the provider wired in.
