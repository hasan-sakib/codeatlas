# Module 13: LangGraph Agent

## Purpose

The conversational control flow that turns a user's question into a grounded, cited answer, implemented as an explicit LangGraph `StateGraph` rather than a linear function — the amount of retrieval/tool-use a turn needs varies (a greeting needs none, a debugging question benefits from a git-blame lookup, a vague question might need a retry with widened search), and the graph makes that branching explicit and inspectable instead of burying it in nested conditionals.

## Why this landed after Modules 14 and 15, not before

Numerically this is Module 13, but most of its nodes are LLM calls (`classify_intent`, `rewrite_query`, `generate_answer`) or conversation persistence (`finalize`) — unlike Module 11→12's single-step reranker gap, building this first would have meant fabricating `LLMPort` and `ManageConversationUseCase` prematurely, both explicitly owned by later-numbered modules. Reordering to build Module 14 (LLM Service) and Module 15 (Conversation Service) first means every node here wires against real, already-verified behavior — no placeholders to replace later.

## Layering

- `app/agent/state.py` — `AgentState` (TypedDict), `Intent`, `ToolCallRecord`.
- `app/agent/graph.py` — `build_agent_graph()`, wiring every node/edge.
- `app/agent/nodes/` — one file per node: `classify_intent`, `rewrite_query`, `retrieve_context`, `rerank`, `assess_sufficiency`, `tool_router`, `call_tool`, `generate_answer`, `cite_sources`, `finalize`, `error_handler`.
- `app/agent/tools/` — `GetFileTool`, `GetGitBlameTool`, `RunSearchTool` (see scope note below on the fourth design-listed tool).
- `app/core/config.py` — `AgentSettings`.
- `app/core/di.py` — `provide_agent_graph(session)` and its tool/dispatcher providers.
- Small additions to Module 14: `prompt_templates/classify_intent.jinja`, `prompt_templates/general_chat.jinja`, and an optional `tool_outputs` block added to `rag_answer.jinja`.

## Scope decision: `get_symbol_references` was not built

The design lists four tools; this module ships three. No symbol-reference index exists anywhere in the codebase — Module 7's parser extracts per-file imports/symbols, but nothing builds a cross-file "who calls this" graph. Fabricating that capability now, just to give `tool_router` a fourth option, would violate the deferral discipline every prior module has followed (Module 11 didn't invent `RerankerPort` early; Module 6's `IndexingTaskDispatcherPort` was a real port with a `Null` stub, not a fake capability). `get_file`, `get_git_blame`, and `run_search` all have genuine backing (chunk/file repositories, `GitPort`, `RetrievalService`) and are fully real.

## Scope decision: `tool_router` is a simple heuristic, not an LLM decision

Ollama's `qwen3:4b` does support real tool-calling (`ollama show qwen3:4b` lists `tools` as a capability), which would be the "correct" way to let the model choose a tool and its arguments. Wiring that through means extending Module 14's `LLMPort` with a structured-output method it doesn't have — real, separate scope, not something to fold into this module silently under time pressure. `tool_router_node`'s v1 heuristic handles exactly one case for real: a `debugging`-intent question with retrieved context gets exactly one `get_git_blame` call (concretely useful — "who last touched this, when" — and needs no LLM-driven argument extraction, since it always targets the top reranked chunk). `get_file` and `run_search` are fully implemented and tested but not yet reachable from this heuristic, wired and ready for a smarter router later.

## Real per-token streaming, verified directly — not deferred to Module 16

Before writing `generate_answer`, I verified LangGraph's `get_stream_writer()` API directly: a plain `async def` node (no LangChain chat-model wrapper needed) can call `get_stream_writer()` and push custom events mid-execution, which a caller receives in real time via `compiled_graph.astream(state, stream_mode=["custom", "values"])`. This meant `generate_answer_node` could stream real tokens through `LLMPort.stream_complete()` today, rather than deferring streaming entirely to Module 16 (Streaming). `get_stream_writer()` raises `RuntimeError` outside a real `.astream()` execution context — a small wrapper (`_get_writer()`) catches that and falls back to a no-op, which is what keeps `generate_answer_node` directly unit-testable (plain state dict + fake ports, no compiled graph required) while still emitting real events when actually run inside a graph. Module 16's future job is exactly what the design says: bridge this graph's `astream(..., stream_mode="custom")` output into SSE wire format — the agent already yields plain dicts (`{"type": "token", "text": ...}`), never framework-specific objects.

## Module 16 is not a blocking dependency (confirmed, not assumed)

Per the design, the agent yields plain events and Module 16 wraps them — the dependency points from Streaming to Agent, not the other way around. Combined with the streaming verification above, this meant Module 13 could be built to completion without Module 16 existing at all.

## Persistence boundary: `finalize` saves the assistant's turn only

`finalize_node` calls `ManageConversationUseCase.append_message(conversation_id, MessageRole.ASSISTANT, final_answer, citations)`. It does not persist the user's own message — whichever future caller invokes this graph (a not-yet-built `AskQuestionUseCase`, likely Module 17's territory) is expected to have already recorded the user's turn before invoking the agent, since the agent's job starts *after* a question exists, not before. This module also doesn't hydrate conversation history itself: `AgentState.messages`/`conversation_summary` are **input** fields set by the caller (via `ManageConversationUseCase.get_context_window()`), not fetched inside the graph — keeping this module self-contained and not reaching backward into Module 15's use case beyond `append_message`.

## Real bugs found by testing against a live Ollama instance, not caught by code review

Every prior module's empirical-verification discipline paid off again here — two real, user-facing bugs were found only by actually running the compiled graph against `qwen3:4b`, not by reasoning about the code:

1. **`generate_answer` returned an empty string for a real RAG prompt.** With `max_tokens=2048` (Module 14's original default), a moderately complex prompt (a retrieved chunk plus a debugging question) caused Qwen3's thinking phase to consume the *entire* token budget — `finish_reason="length"`, `response=""`. This is a sharper version of the risk Module 14's docs already flagged ("1024 is a floor, not a safe default for longer prompts") — verified here that even 2048 isn't always enough. Fixed two ways: (a) `generate_answer_max_tokens` raised to 4096 (with `OllamaSettings.num_ctx` raised to 16384 to keep headroom above it, verified to load without issue, ~5.1GB resident), and (b) `generate_answer_node` now detects an empty token stream and returns an honest fallback message ("wasn't able to produce an answer... try rephrasing") instead of silently returning nothing — a real robustness fix, not just a bigger budget.
2. **`GENERAL_CHAT` intent produced a nonsensical refusal.** A casual "thanks for the help!" was still routed through `rag_answer.jinja`'s system prompt, which explicitly instructs the model to refuse when there's no retrieved context — producing "The context does not contain enough information to answer the question" for a simple thank-you. Fixed by adding `general_chat.jinja` (a lightweight, no-refusal prompt) and branching `generate_answer_node` on `state["intent"] == Intent.GENERAL_CHAT` before rendering. Both fixes were verified by re-running the exact same scenario against the real model afterward and confirming a correct, natural response.

A third real API-behavior investigation (not a bug, a design input): tried Ollama's `raw: true` option (bypasses chat templating entirely) as a possible fix for the thinking-token-exhaustion problem — it did produce non-empty output, but the reasoning trace is no longer separated into a `thinking` field at all (it's inlined into the visible response, verbose and rambling). Not adopted: fixing this properly would mean adding a `raw` mode to Module 14's `OllamaAdapter`, a real adapter-level change belonging to that module, not something to bolt on here. Documented as a known future mitigation path.

## `assess_sufficiency` deliberately has one honest signal, not a fake threshold

The design's language suggests a "relevance-score threshold." This wasn't built: `bge-reranker-base`'s raw scores aren't a calibrated, bounded quantity — Module 12 measured 0.044 vs. 0.000037 for a relevant/irrelevant pair, nothing resembling a [0,1] probability with an obvious cutoff. Inventing a threshold number would be arbitrary precision dressed up as a principled one. `assess_sufficiency_node` uses the one signal that's actually honest: whether `reranked_chunks` is empty at all.

## Error handling: manual state-checking, not LangGraph's automatic exception routing

Per the design's own explicit recommendation, each risky node (`classify_intent`, `rewrite_query`, `retrieve_context`, `generate_answer`) catches its own exceptions and returns `{"error": ...}` instead of letting them propagate; a shared `_route_or_error(state, happy_path=...)` conditional-edge helper checks `state.get("error")` after each of those nodes and routes to `error_handler` if set. This is deterministic and directly testable (assert the returned dict, no need to mock LangGraph's internal exception machinery). `call_tool_node` handles tool failures differently and intentionally: a tool raising an exception becomes a `ToolCallRecord.error` (data the LLM can reason about — "blame lookup failed, no clone available"), not a graph-level error, since one failed tool shouldn't abort an otherwise-answerable turn.

## Testing notes

- 66 new unit tests across `tests/unit/agent/`: one file per node (classify_intent's lenient label-parsing and default-to-CODE_QA behavior; rewrite_query's history-based LLM-skip; retrieve_context's k1/k2 widening math; rerank's empty-input short-circuit; assess_sufficiency's single honest signal; tool_router's debugging-only heuristic and already-called/cap guards; call_tool's per-tool dispatch and error-as-data handling; generate_answer's template branching, tool-output inclusion, and empty-response fallback; cite_sources's context_chunks-not-reranked_chunks sourcing; finalize's persistence call; error_handler's message formatting), one file per tool (all three tools tested with fakes for their repository/port dependencies), and `test_graph.py` — a full-graph integration-style suite using a fast, deterministic `ScriptedLLM` (no real network) that codifies every scenario originally verified by hand against the live model: CODE_QA happy path with citations, GENERAL_CHAT skipping retrieval entirely, DEBUGGING triggering exactly one tool call, the retrieval retry loop (both the widen-then-succeed and exhaust-and-proceed-anyway paths), LLM failure routing to `error_handler` while still finalizing, and real per-token custom-stream-event emission via `astream(..., stream_mode=["custom", "values"])`.
- All unit tests are mocked at the port boundary (`FakeLLMPort`, `FakeRetrievalService`, `FakeRerankerPort`, `FakeManageConversationUseCase`, `FakeTool`) — no real Ollama/Postgres/Qdrant in the checked-in suite, following the precedent of every prior module. The *real* model verification — the two bugs above, the streaming confirmation, the `raw:true` investigation — was performed by hand against a live local Ollama instance during development and is documented here rather than baked into `pytest`.
- `pytest -q`: 325 passed (66 new). `mypy app`: no issues, 174 source files. `ruff`/`black`: clean. `pre-commit run --all-files`: clean.
- No live-server test — this module has no HTTP surface of its own (same reasoning as Modules 7-15); it's consumed by a future module's endpoint (`app/api/routers/conversations.py`, not yet built).
