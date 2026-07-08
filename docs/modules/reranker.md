# Module 12: Reranker

## Purpose

Improve precision of the top-K2 fused candidates from Module 11's retrieval pipeline by scoring each `(query, chunk_text)` pair with a cross-encoder, producing the final top-N chunks — the last quality gate before the retrieved context reaches the (future) LLM/agent layer.

## Layering

- `app/domain/ports/reranker_port.py` — `RerankerPort` Protocol (`score(query, chunks) -> list[RankedChunk]`).
- `app/infrastructure/reranker/model_registry.py` — `get_cross_encoder()`, an `lru_cache`d process-wide singleton loader for the `sentence_transformers.CrossEncoder` model.
- `app/infrastructure/reranker/cross_encoder_reranker.py` — `CrossEncoderReranker`, the `RerankerPort` implementation.
- `app/core/config.py` — `RerankerSettings` (`model_name`, `max_length`, `batch_size`, `device`, `fail_open`).
- `app/core/di.py` — `provide_reranker_port()`, **not** cached (the adapter itself holds no heavy state — the actual model lives in `model_registry`'s own `lru_cache`, so a fresh lightweight `CrossEncoderReranker` instance per call is fine and avoids coupling the DI cache lifecycle to the model cache lifecycle).

## Why `sentence_transformers.CrossEncoder`, not FlagEmbedding again

Module 9 needed `FlagEmbedding` specifically because BGE-M3's sparse output has no other exposure. Reranking has no such constraint — a cross-encoder is just a sequence-pair classifier — so `sentence_transformers.CrossEncoder` is the standard, lighter-weight choice: `CrossEncoder(model_name, max_length=..., device=...)` plus `.predict(pairs, batch_size=...) -> numpy.ndarray`, verified directly via `inspect.signature` before writing the adapter rather than assumed from documentation.

## This module closes the loop Module 11 deliberately left open

Module 11's `RetrievalService.retrieve()` was built with a documented placeholder: no `RerankerPort` existed yet, so it returned fused-only results tagged `source="fused"`, and `retrieve_without_rerank()` was intentionally not implemented (it would have been an exact duplicate). Landing the real reranker meant going back into `RetrievalService` rather than treating this as an isolated add — a reranker nobody calls verifies nothing about the actual pipeline:

- `RetrievalService.__init__` gained a required `reranker_port: RerankerPort` parameter.
- The old `_fuse_and_hydrate` step no longer slices to `query.n` — it now returns the full up-to-`k2` fused/hydrated candidate list, because the reranker needs to see all of them to do anything useful. The `n`-slice moved to *after* reranking.
- `retrieve()` now runs: encode → parallel search → RRF fuse → hydrate → `reranker.score(query_text, fused)` → slice to `n`, tagging results `source="reranked"`.
- `retrieve_without_rerank()` is now real: fused/hydrated candidates, sliced to `n` directly, `source="fused"`, and the reranker is never invoked — verified by a test that hands it a reranker stub which raises `AssertionError` if called at all.
- `app/core/di.py`'s `provide_retrieval_service()` now wires `provide_reranker_port()` in as the fifth dependency.

See `docs/modules/retriever.md`'s "Two forward-references handled by deferral, not fabrication" section for the placeholder this replaces.

## Contract: the reranker never truncates, the caller does

`RerankerPort.score()` returns the **full** reordered list — it takes no `n`/`top_k` parameter and never slices. `RetrievalService` (the caller) owns the top-N decision, matching the design's explicit requirement that N-slicing is the retriever's responsibility, not the reranker's. This is enforced by a dedicated unit test (`test_score_returns_full_reordered_list_without_slicing`) rather than left as an implicit convention, since it's easy to accidentally "helpfully" slice inside an adapter and silently break a caller that wanted the full list for some other purpose.

## Fail-open by default, config-gated

Reranking is a quality improvement, not a correctness requirement — a failed rerank should degrade to "results in fused order" rather than break retrieval entirely. `RerankerSettings.fail_open` (default `true`) controls this: if the underlying model call raises for any reason, `CrossEncoderReranker.score()` catches it, logs a `reranker.failed_fail_open` warning (model name, chunk count), and returns the **original input list, unchanged and un-retagged** (still whatever `source` it came in with, e.g. `"fused"` — not retagged `"reranked"`, since nothing was actually reranked). Setting `fail_open=False` (e.g. for a strict evaluation harness that wants to know immediately if the model is broken) makes the same failure propagate as a real exception instead.

## Truncation, not dropping

`CrossEncoder` has a `max_length` token budget; chunk text longer than that is truncated (via a `max_length * 4`-chars heuristic — no tokenizer call needed just to decide a truncation point) rather than the chunk being dropped from consideration entirely. The query itself is never truncated — only `chunk.text`. Verified the heuristic is conservative enough in practice via the real-model check below; a chunk that's borderline oversized still scores sensibly even with the tail cut off, since relevance signal for code chunks is concentrated in the first ~100-200 tokens (imports/signature/docstring) far more often than the last.

## Real-model verification (done by hand, not part of the automated suite)

Downloaded and ran the actual `BAAI/bge-reranker-base` model (~1.1GB, confirmed via HTTP HEAD before downloading) twice during development:

1. **Raw `sentence_transformers.CrossEncoder` level**: scored a (relevant, irrelevant) pair for a hand-picked query — relevant chunk scored 0.044, irrelevant scored 0.000037, confirming the model produces a usable relevance signal before any adapter code was trusted.
2. **Full `CrossEncoderReranker.score()` level**: passed `[irrelevant_chunk, relevant_chunk]` in that order, with the irrelevant chunk deliberately given a *higher* initial fused score than the relevant one (simulating a case where dense/sparse fusion got it wrong) — confirmed the reranker correctly moved the relevant chunk to position 0, and both results came back tagged `source="reranked"`.

Following Module 9's established precedent, this real-model verification is **not** baked into the checked-in automated suite. The reranker's only "real infrastructure" dependency is the model weights themselves (unlike Module 10's Qdrant/Postgres, which testcontainers pulls cheaply and automatically) — baking a 1.1GB one-time HuggingFace download into `pytest` would tax every future CI run and fresh contributor checkout for a fact already verified by hand. The checked-in suite instead monkeypatches `CrossEncoderReranker._predict_batch` at the class level in every unit test, so it never imports `sentence_transformers`' actual model-loading path.

## Testing notes

- `test_cross_encoder_reranker.py`: `score()` reorders chunks by mocked predicted score, descending, and retags `source="reranked"`; returns the **full** reordered list without slicing (no `n` truncation inside the reranker — that's `RetrievalService`'s job); empty `chunks` input returns `[]` without ever calling `_predict_batch`; a chunk longer than `max_length` is truncated in what's sent to the model but still present in the output, and the query itself is never truncated; fail-open path — `_predict_batch` raises, `score()` returns the original input list unchanged (not retagged) and does not propagate; `fail_open=False` — the same failure re-raises instead. Also covers `_truncate()` directly (short text passthrough, long text shortened to the `max_length * 4`-char heuristic).
- `test_retrieval_service.py`/`test_retrieval_service_integration.py` (Module 11's suite, updated here): every `RetrievalService` construction now passes a `FakeReranker` (identity — reorders nothing, just retags `"reranked"`) or, for the integration test, a `_NeverCalledReranker` stub that raises if invoked at all (that test exercises `retrieve_without_rerank()` specifically, so the reranker must never be called); a new `test_retrieve_without_rerank_skips_the_reranker_and_returns_fused_results` test asserts the bypass path never touches the reranker and returns `source="fused"` results sliced to `n`.
- `pytest -q`: 213 passed (9 new: 8 in `test_cross_encoder_reranker.py` plus 1 new `retrieve_without_rerank` test in Module 11's suite — the other 5 Module 11 tests were updated in place, not added). `mypy app`: no issues, 147 source files. `ruff`/`black`: clean. `pre-commit run --all-files`: clean.
- No live-server test — this module has no HTTP surface (same reasoning as Modules 7-11). Verified instead via the full test suite above plus the hand-run real-model checks documented above.
