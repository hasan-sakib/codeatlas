from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


class NullConversationSummaryDispatcher:
    """Placeholder `ConversationSummaryDispatcherPort` — no Celery
    worker/broker exists yet (mirrors NullIndexingTaskDispatcher's
    reasoning exactly).

    Persists no state and enqueues nothing; it exists only so
    ManageConversationUseCase has something to call today. Every call
    logs a warning so this is never mistaken for a working queue
    integration. SummarizeConversationUseCase itself is fully real and
    independently tested — only the automatic trigger is inert. Replace
    with a real Celery-backed adapter once a worker/broker exists.
    """

    async def dispatch(self, conversation_id: UUID) -> None:
        logger.warning(
            "conversation_summary_dispatch.not_implemented",
            conversation_id=str(conversation_id),
            detail="No queue is wired up yet — summarization will not run automatically.",
        )
