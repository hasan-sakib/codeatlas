# Module 15: Conversation Service

## Purpose

Owns the conversation/message lifecycle: creating conversations, appending messages, hydrating a bounded context window for the (future) agent, and triggering rolling summarization once a turn-count threshold is crossed. This is the second module — after Module 14 (LLM Service) — pulled ahead of its numeric order specifically to unblock Module 13 (LangGraph Agent), whose `finalize` node needs real message persistence and whose graph entry needs real history hydration.

## Why this module turned out small

While starting Module 13's design work, a survey of the codebase found that Module 4 (Database) had already built the full `Conversation`/`Message` entities, `ConversationRepository`/`MessageRepository` ports, and real (if untested — see below) SQLAlchemy implementations, anticipating this module explicitly in a code comment (`app/domain/entities/conversation.py`: *"Module 15 (Conversation Service)'s ConversationRepositoryPort design requires..."*). So Module 15's actual remaining scope is just the **application-layer use cases** — `ManageConversationUseCase` and `SummarizeConversationUseCase` — not a full module's worth of new entities/persistence. This made "build the real dependency" (the same call made for Module 14) a small, well-scoped decision rather than a large detour.

## Layering

- `app/application/use_cases/chat/manage_conversation.py` — `ManageConversationUseCase` (`create_conversation`, `append_message`, `get_context_window`).
- `app/application/use_cases/chat/summarize_conversation.py` — `SummarizeConversationUseCase` (`execute`).
- `app/domain/ports/conversation_summary_dispatcher.py` — `ConversationSummaryDispatcherPort`.
- `app/infrastructure/queue/null_conversation_summary_dispatcher.py` — `NullConversationSummaryDispatcher`.
- `app/domain/exceptions.py` — `ConversationNotFoundError` (new).
- `app/core/config.py` — `ConversationSettings` (`summary_threshold`, `context_window_turns`).
- `app/core/di.py` — `provide_manage_conversation_use_case`, `provide_summarize_conversation_use_case`, `provide_conversation_summary_dispatcher`, `provide_prompt_renderer`.
- Already existed from Module 4 (consumed, not rebuilt, here): `app/domain/entities/conversation.py`, `app/domain/entities/message.py`, `app/domain/ports/conversation_repository.py`, `app/domain/ports/message_repository.py`, `app/infrastructure/db/repositories/sqlalchemy_{conversation,message}_repository.py`.

## The summarization dispatcher mirrors Module 6's established deferral pattern exactly

No Celery worker/broker exists yet — the design calls for summarization to run asynchronously once a turn-count threshold is crossed, but there's nowhere real to dispatch that task to. Rather than fabricate Celery wiring prematurely, `ConversationSummaryDispatcherPort` + `NullConversationSummaryDispatcher` mirror Module 6's `IndexingTaskDispatcherPort` + `NullIndexingTaskDispatcher` precedent exactly: `ManageConversationUseCase.append_message` calls `dispatcher.dispatch(conversation_id)` when the threshold is crossed, and the DI-wired default logs a warning and does nothing. `SummarizeConversationUseCase` itself is fully real and independently tested — only the automatic trigger is inert until a real queue exists.

## Two real bugs this module's testing caught in code Module 4 had built but never tested

Module 4's own docs are explicit that its testing scope covered the migration/FK-cascade/chunk-round-trip but not `SqlAlchemyConversationRepository`/`SqlAlchemyMessageRepository` directly — those were built ahead of schedule as part of "define the full schema now" and left for whichever module actually needed them to verify. Since `ManageConversationUseCase`/`SummarizeConversationUseCase` depend on them directly, this module closed that gap with real Postgres integration tests (`tests/integration/infrastructure/db/test_sqlalchemy_conversation_and_message_repository.py`) — and found:

1. **A bare `ValueError` where every other domain-level failure in this codebase raises a `DomainError` subclass.** `SqlAlchemyConversationRepository.increment_turn_count` raised `ValueError(f"Conversation {conversation_id} not found")` for an unknown id — inconsistent with `WorkspaceNotFoundError`/`RepositoryNotFoundError`/etc. everywhere else. Fixed to raise the new `ConversationNotFoundError` instead, same behavior (still raised before any flush), now matching convention. `ManageConversationUseCase.append_message` deliberately does not duplicate this existence check — it lets the repository's own check raise, rather than checking twice.
2. **`MessageModel.created_at`'s `server_default=func.now()` produced identical timestamps for every message appended within one session/request.** Verified directly against a real Postgres instance: `SELECT now(), now()` within one transaction returns the *same* value twice — Postgres's `now()` is transaction-scoped, not per-statement. Since appending several messages in one request/session is the normal case, `MessageRepository.list_recent`'s `ORDER BY created_at DESC` had no way to break ties correctly, and two tests reproduced genuinely wrong chronological ordering before the fix (`test_message_append_and_list_recent_round_trips_citations_in_chronological_order` returned messages in the wrong order; `test_message_list_recent_respects_limit_keeping_the_most_recent` returned the wrong subset entirely). Fixed by switching to `func.clock_timestamp()` (true per-statement wall-clock time), with a new Alembic migration (`0002_messages_created_at_clock_timestamp.py`) so a real deployed database gets the same fix — verified `alembic upgrade head` then `alembic check` against a fresh Postgres container reports "No new upgrade operations detected," confirming the model and migration now agree. This was caught by running real tests against real Postgres, not by code review — the bug is invisible in a single-message test and only appears with multiple appends in one transaction, exactly the shape a real conversation has.

## `get_context_window`'s contract: summary and recent messages are additive, not exclusive

`get_context_window(conversation_id, max_turns)` returns `(summary, recent_messages)` where `summary` covers everything *older* than what `recent_messages` already carries verbatim — a caller (the future agent) uses both together to build the LLM's context, never picks one or the other. `Conversation.summary` and `Message` rows aren't mutually exclusive views of the same data; `summary` exists specifically to keep prompt size bounded once a conversation has more history than fits in `context_window_turns` recent messages.

## `append_message` computes a real token count via Module 14's tokenizer

`Message.token_count` (a field the schema already had, unused until now) is computed via `token_utils.count_tokens()` at append time — a small, direct integration of Module 14's real Qwen3 tokenizer rather than leaving the field at its default `0`. This gives future prompt-budget logic (context-window trimming, `truncate_to_budget`) a real number to work with instead of nothing.

## Testing notes

- `test_sqlalchemy_conversation_and_message_repository.py` (integration, real Postgres via testcontainers): full CRUD round-trip for `SqlAlchemyConversationRepository` (add/get/list_for_user with workspace and soft-delete filtering/increment_turn_count/update_summary/soft_delete) and `SqlAlchemyMessageRepository` (append/list_recent chronological ordering and limit behavior, JSONB citation round-trip fidelity) — the two real bugs above were found and fixed via this file.
- `test_manage_conversation.py`: conversation creation defaults; `append_message` persists a message with a real (non-mocked) computed token count, stores citations when given, increments turn count, propagates `ConversationNotFoundError` from the repository rather than double-checking; summarization dispatch fires exactly at the threshold boundary (turn 8→9 doesn't, 9→10 does, 10→11 doesn't again — mirroring the design's own stated boundary-testing language); `get_context_window` returns `(summary, messages)` correctly and raises for both an unknown and a soft-deleted conversation.
- `test_summarize_conversation.py`: uses the **real** `PromptRenderer` (cheap, no model) with a `FakeLLMPort` — verifies the rendered prompt actually contains the existing summary and prior message content (not just that some prompt was sent), that the summary block is correctly omitted when there's no prior summary, that the result is persisted via `update_summary`, and that both not-found conditions raise.
- `pytest -q`: 259 passed (23 new). `mypy app`: no issues, 156 source files. `ruff`/`black`: clean (one line-length wrap). `pre-commit run --all-files`: clean. `alembic upgrade head` + `alembic check` against a fresh Postgres container: clean, no drift.
- No live-server test — this module has no HTTP surface (same reasoning as Modules 7-14); its use cases are consumed directly by Module 13's agent and, later, Module 17's REST API.
