# Module 14: LLM Service

## Purpose

The single abstraction point for every LLM call in CodeAtlas, backed by a local Ollama instance running `qwen3:4b`. Every future caller — Module 13's agent nodes (`classify_intent`, `rewrite_query`, `generate_answer`), Module 15's conversation summarizer — talks to it exclusively through `LLMPort`, never through raw HTTP calls to Ollama. That's what makes swapping to a bigger local model or a cloud provider later a pure adapter swap with zero changes to calling code.

## Why this module was pulled ahead of Module 13

Module 13 (LangGraph Agent) is next in the design's numbering, but most of its nodes (`classify_intent`, `rewrite_query`, `generate_answer`) are LLM calls by definition — unlike Module 11→12's single-step reranker gap or Module 11→20's metrics gap, this wasn't a narrow one-piece deferral. Building Module 13 first would have meant either fabricating `LLMPort` prematurely (a port this design explicitly assigns to Module 14) or stubbing the majority of the agent's graph. Reordering to build the real `LLMPort` first means Module 13 will wire against verified, real behavior instead of a placeholder.

## Layering

- `app/domain/value_objects/llm_completion_result.py` — `LLMCompletionResult` (`text`, `prompt_tokens`, `completion_tokens`, `finish_reason`).
- `app/domain/ports/llm_port.py` — `LLMPort` Protocol (`complete`, `stream_complete`).
- `app/domain/exceptions.py` — `LLMUnavailableError`.
- `app/infrastructure/llm/token_utils.py` — `count_tokens()`, `truncate_to_budget()`.
- `app/infrastructure/llm/prompt_renderer.py` — `PromptRenderer`, plus `prompt_templates/rag_answer.jinja` / `query_rewrite.jinja` / `summarize.jinja`.
- `app/infrastructure/llm/ollama_adapter.py` — `OllamaAdapter`, the `LLMPort` implementation.
- `app/core/config.py` — `OllamaSettings` extended with `num_ctx`, `max_retries`, `retry_backoff_seconds` (base URL/model/timeout already existed from Module 2).
- `app/core/di.py` — `provide_llm_port()`, **not** cached (the adapter holds only config values — base URL, model name, timeouts — no in-process model weights, unlike `BgeM3Adapter`/`CrossEncoderReranker`, so a fresh instance per call costs nothing).

## Real-API findings this module's design is built on

Verified by hand against a live `qwen3:4b` Ollama instance (0.30.11) running locally, not assumed from documentation — the same discipline that caught Qdrant's removed `.search()` method in Module 10.

1. **Qwen3's chain-of-thought and final answer are separate JSON fields, not something to strip from text.** Every `/api/generate` response — streaming or not — carries `thinking` (the chain-of-thought) and `response` (the actual answer) as distinct fields. `OllamaAdapter` reads only `response` and never forwards `thinking`, so a reasoning trace never reaches a user-facing caller. Streaming confirmed the same split holds per-line: of 310 NDJSON lines in one real call, 307 carried a `thinking` delta with an empty `response`, and only 3 carried real `response` text.
2. **Disabling thinking is unreliable in this environment — don't rely on it.** The documented `think: false` request field hung indefinitely on `/api/generate` and was silently ignored on `/api/chat` (with the `<think>...</think>` block leaking straight into `message.content` instead of being suppressed). The classic `/no_think` prompt-suffix trick also failed to produce any answer text within a 200-token budget. This adapter deliberately never sends `think` at all — consuming `response`/discarding `thinking` sidesteps the reliability problem entirely regardless of whether thinking is actually suppressed.
3. **`num_predict` (→ `max_tokens`) bounds thinking + answer combined, not just the answer.** Verified directly: a trivial "say hello in exactly 3 words" prompt with `max_tokens=500` spent the *entire* budget on thinking and returned `text=""` with `finish_reason="length"` — no answer at all. `max_tokens=1024` was enough headroom (827 tokens actually used, natural `finish_reason="stop"`). This is documented prominently in `OllamaAdapter`'s docstring: 1024 is a floor for this model with thinking on, not a safe default for longer or more context-heavy prompts (Module 13's `generate_answer` node should budget generously, e.g. 2048+).
4. **Ollama's server-launch default context window is far smaller than the model supports.** `ollama ps` confirmed a running context of 4096 tokens against this machine's launch flags, versus the model's advertised 262144 maximum. `options.num_ctx` must be set explicitly on every request — verified that passing it actually resizes the loaded model's KV cache (context 4096→8192, memory 3.2GB→3.9GB after a request with `num_ctx: 8192`).
5. **`max_tokens`/`temperature` are not top-level request fields** — they map to `options.num_predict` / `options.temperature`.
6. **Real streaming is genuinely incremental, not buffered.** `client.send(request, stream=True)` returns as soon as headers arrive (~0.2ms in a real call) without waiting for the body; `response.aiter_lines()` then yields NDJSON lines as they arrive. An earlier draft of this adapter buffered the *entire* response body before returning anything from `stream_complete()` — functionally identical to `complete()` and defeating the entire purpose of the streaming API. Caught by actually timing `stream_complete()` against the live server and finding the "first chunk" timestamp equaled the "total elapsed" timestamp, not by code review.

## The token-budget consequence: `PROMPT_TEMPLATE_OVERHEAD_TOKENS`

`token_utils.count_tokens()` uses the real `Qwen/Qwen3-4B` tokenizer (loaded the same way Module 8/9 load BGE-M3's — via the lightweight `tokenizers` package, not full `transformers`). Verified its token ids are an exact substring of what Ollama's own `context` field reports for a prompt containing that text — the only gap is the chat-template control tokens (`<|im_start|>user`, `<|im_end|>`, etc.) that Ollama wraps around every prompt before tokenizing, which this tokenizer doesn't add. `OllamaAdapter.PROMPT_TEMPLATE_OVERHEAD_TOKENS` (32, deliberately generous) reserves headroom for that wrapping so a caller budgeting a prompt against `num_ctx` doesn't silently overflow it.

## `truncate_to_budget`'s two modes are about which end to trim, not re-ranking

The design's signature (`keep: Literal["newest", "highest_relevance"]`) takes a plain `list[str]` with no relevance scores attached, so "highest_relevance" can't mean *compute* relevance — there's nothing to compute it from. The only interpretation that makes sense given the actual signature: the caller has already ordered `segments` meaningfully, and `keep` says which end to protect while trimming from the other:

- `keep="newest"`: input is oldest-to-newest (conversation turns) — trims from the front, keeping the most recent turns. Used for conversation history.
- `keep="highest_relevance"`: input is most-relevant-to-least (reranked chunks, already sorted by Module 12) — trims from the back, keeping the most relevant chunks.

Both modes stop at the *first* segment (from whichever end) that doesn't fit — a greedy fill, not "skip an oversized one and try a smaller one further along," since skipping would create gaps in conversation history or an arbitrary-looking hole in retrieved context.

## Retry semantics: bounded, non-retryable errors short-circuit, streaming never re-plays

`AsyncRetrying` (tenacity) wraps only connection-establishment for both `complete()` and `stream_complete()` — retryable failures are `httpx.ConnectError`/`httpx.TimeoutException` and 5xx status codes; a 4xx (bad request, unknown model) is deliberately **not** retried, since retrying a request that will never succeed just wastes the retry budget and adds latency before the caller finds out. Both retryable-exhausted and non-retryable failures surface as `LLMUnavailableError` — the port docstring is precise about this: "immediately on a non-retryable error... without spending the retry budget," not "after exhausting retries" in that case, since a single failed attempt isn't really an exhausted budget.

For `stream_complete()` specifically, retries are scoped to *opening* the stream (headers received, status checked) — once real text has started yielding to the caller, a retry would replay/duplicate already-emitted output, so a mid-stream failure raises `LLMUnavailableError` directly with no retry attempt at all.

## Testing notes

- `test_token_utils.py`: empty-string is zero tokens, monotonic scaling, a hand-verified regression pin against the real Qwen3 tokenizer (matching Module 8's established precedent of testing tokenizer output directly rather than mocking it — the tokenizer itself is a small download, unlike a full model); both `truncate_to_budget` trim directions, a zero-budget case, and an under-budget passthrough.
- `test_prompt_renderer.py`: all three templates render correctly against a full fixture context; the optional `conversation_summary`/`existing_summary` blocks are correctly omitted/included; a missing required variable raises `jinja2.UndefinedError` (via `StrictUndefined`) rather than silently rendering an empty string into a prompt sent to the LLM.
- `test_ollama_adapter.py`: mocked entirely at the `httpx.AsyncClient` boundary via `httpx.MockTransport` (a real `AsyncClient`/`Response` with a fake transport, not a hand-rolled fake — chosen over stubbing `httpx.AsyncClient` itself so `raise_for_status()`/`aiter_lines()` exercise their real implementations against synthetic NDJSON bytes). Covers: successful `complete()` parsing, correct `options.num_predict`/`options.temperature`/`options.num_ctx` mapping, retry-then-succeed on `ConnectError` and on a 503, exhausted-retries raising `LLMUnavailableError` with the expected attempt count, a 400 short-circuiting after exactly one attempt (no wasted retries), `stream_complete()` yielding only non-empty `response` chunks in order while silently dropping `thinking`-only lines, and both streaming failure paths (`ConnectError`, non-retryable 4xx).
- No integration test against a real Ollama instance is included in the checked-in suite, following the precedent set by Module 9 (BGE-M3) and Module 12 (cross-encoder reranker): `qwen3:4b` is a 2.5GB one-time pull with no testcontainers equivalent, and CI runners won't have it pre-pulled. Real-model verification was instead performed by hand against a live local Ollama instance (see findings above) and is documented here rather than baked into `pytest`.
- `pytest -q`: 236 passed (23 new). `mypy app`: no issues, 151 source files. `ruff`/`black`: clean (two pre-existing/incidental fixes bundled in: a line-length wrap in the new retry config, and a ternary simplification in `truncate_to_budget`). `pre-commit run --all-files`: clean.
- No live-server test — this module has no HTTP surface of its own (same reasoning as Modules 7-12); it's a backend adapter consumed by a future module's endpoints.

## Incidental fix bundled into this module

While adding this module's dependencies (`jinja2`, `tenacity`), discovered `sentence-transformers` — imported directly by Module 12's `CrossEncoderReranker` — was never declared in `pyproject.toml`'s dependency list, only present transitively. Declared it explicitly (`>=3.2,<4`, matching the installed `3.4.1`). Upgrading it also made a `# type: ignore[arg-type]` on `CrossEncoder.predict(...)` (added in Module 12 for an older transitive version's overly broad parameter typing) genuinely unused under mypy — removed it rather than leaving a dead ignore comment.

## Follow-up from Module 13

Two settings changed after Module 13's real-model testing surfaced sharper versions of the risks already flagged above: `OllamaSettings.num_ctx` raised from 8192 to 16384, and a new `AgentSettings.generate_answer_max_tokens` (4096) was added — a real RAG-shaped prompt (retrieved chunk + question) was enough to exhaust a 2048-token budget entirely on thinking, producing an empty answer. Module 13 also added `classify_intent.jinja` and `general_chat.jinja` to `prompt_templates/`, and a `tool_outputs` block to `rag_answer.jinja` — see `docs/modules/langgraph_agent.md` for the two real bugs this caught (empty answers, and a wrong refusal response for casual greetings) and the `raw: true` mitigation investigated but not adopted here.
