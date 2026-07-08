from typing import Protocol
from uuid import UUID


class ConversationSummaryDispatcherPort(Protocol):
    async def dispatch(self, conversation_id: UUID) -> None:
        """Trigger asynchronous re-summarization of conversation_id.

        Kept abstract so ManageConversationUseCase doesn't hard-depend on
        Celery's wire format — the real Celery-backed adapter is
        registered once a worker/broker exists (see
        NullConversationSummaryDispatcher for the current placeholder).
        """
        ...
