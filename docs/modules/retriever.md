# Module 11: Retriever

## Purpose

A single, framework-agnostic orchestration point for hybrid retrieval — dense + sparse Qdrant search, Reciprocal Rank Fusion, Postgres hydration — meant to be consumed identically by the future LangGraph agent's `retrieve_context` node and the stateless `/search`/`/ask` REST endpoints, so retrieval behavior never diverges between the conversational and one-shot code paths.

## Layering

- `app/domain/value_objects/retrieval_query.py` — `RetrievalFilters`, `RetrievalQuery`.
- `app/domain/value_objects/ranked_chunk.py` — `RankedChunk`.
- `app/application/services/fusion.py` — `reciprocal_rank_fusion()`, a pure function.
- `app/application/services/retrieval_service.py` — `RetrievalService`, the orchestrator.
- `app/core/di.py` — `provide_retrieval_service(session)`, not cached (composes session-scoped repositories with the process-wide embedding/vector-store singletons).

This is also the first module to introduce `app/application/services/` and confirm there's no existing `dto/` convention to match — the `use_cases/<domain>/<verb>.py` layout used by auth/workspaces/indexing doesn't fit an orchestration service consumed by multiple callers, so this is a fresh (but structurally obvious) addition.

## A small, justified addition to Module 4's `FileRepository`

`SearchResult` (Qdrant's return type, Module 10) carries only `chunk_id` and `score` — no payload. Hydrating a `RankedChunk.file_path` requires joining `Chunk.file_id` against `File.path`, and `FileRepository` only had `get_by_id` (singular). Added `get_by_ids(file_ids) -> list[File]`, mirroring the batch method that already existed on `ChunkRepository` — avoids N+1 queries on a path with a documented p95 latency budget (DESIGN.md NFR-1: retrieval candidates within 1.5s at p95). Same category of small, precedented addition as Module 5's `revoke_if_active` and Module 11's own use of `ChunkRepository.get_by_ids`.

## Two forward-references handled by deferral, not fabrication

Module 11 numerically precedes two modules it conceptually depends on:

1. **Module 12 (Reranker) doesn't exist yet**, but the design's `RetrievalService.retrieve()` interface explicitly threads a `RerankerPort.score()` call between hydration and the final N-slice. Rather than invent `RerankerPort` prematurely (it's Module 12's file to own, per the design's own directory listing), `retrieve()` currently does encode → parallel search → RRF fuse → hydrate → slice-to-N directly, returning results tagged `source="fused"` instead of `"reranked"`. The design's second method, `retrieve_without_rerank()`, is intentionally not implemented yet — it would be an exact duplicate of `retrieve()` in this interim state, and only becomes a meaningful, distinct method once there's an actual rerank step to bypass. When Module 12 lands: add a rerank step, retag results `"reranked"`, and introduce `retrieve_without_rerank()` as the real bypass.
2. **Module 20 (Monitoring) doesn't exist yet**, so `retrieve()` emits a `retrieval.completed` structlog event (dense/sparse hit counts, result count, duration) instead of a `retrieval_duration_seconds` Prometheus metric. Swap in the real metric when Module 20 lands; the log line already carries everything the metric would need.

## `path_prefix` filtering is post-hydration, not pushed into Qdrant

Qdrant's `file_path` payload field is keyword-indexed for exact match only (Module 10's `_PAYLOAD_INDEXES`) — it can't do prefix matching without a different index type. `RetrievalFilters.path_prefix` is applied in Python after hydration, against whichever fused top-K2 candidates Postgres returned. Accepted trade-off, documented rather than silently approximated: a prefix filter can only ever narrow *within* whatever K1/K2 the vector search already surfaced — it can't recover a relevant chunk the dense/sparse search ranked outside that window. `language` and `symbol_kind`, by contrast, *are* pushed down into the Qdrant filter directly, since both are exact-match keyword-indexed fields matching Module 10's schema precisely.

## Testing notes

- `test_fusion.py`: disjoint sets, overlapping-id score boosting (hand-computed against the `1/(k+rank)` formula), empty inputs, descending sort order.
- `test_retrieval_service.py` (fakes for all four ports): dense/sparse calls receive the correct `workspace_id` and pushed-down filters (`is_active`/`embedding_version` always present, `language`/`symbol_kind` only when set); hydration preserves fused rank order even though the fake `ChunkRepository.get_by_ids` deliberately returns rows in *reverse* order (proving the service re-sorts rather than trusting Postgres's return order); zero-hit case returns `[]` without ever calling the repositories; `path_prefix` filtering excludes non-matching hydrated results; final slice respects `n`.
- `test_retrieval_service_integration.py` (real Postgres + real Qdrant via testcontainers, stubbed embedding step): seeds a full User→Workspace→Repository→File→Chunk chain in Postgres and three hand-crafted orthogonal vectors in Qdrant, then runs `retrieve()` end-to-end with a query vector identical to one seeded vector — asserts that chunk ranks first, with its real file path and content correctly hydrated from Postgres. The embedding step is stubbed with a known vector (not the real BGE-M3 model) for the same reason Module 9's integration tests avoid it: deterministic, network-independent, and doesn't pay a real-model-load tax on every test run.
- `pytest -q`: 204 passed (10 new). `mypy app`: no issues, 141 source files. `ruff`/`black`: clean. `pre-commit run --all-files`: clean.
- No live-server test — this module has no HTTP surface yet (no `/search`/`/ask` router exists; that's a later module). Verified instead via the full test suite above plus a confirmed clean app boot with `provide_retrieval_service` wired in.
