from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.entities.conversation import Conversation
from app.domain.entities.message import Citation, Message, MessageRole
from app.domain.exceptions import ConversationNotFoundError
from app.domain.ports.conversation_repository import ConversationRepository
from app.domain.ports.conversation_summary_dispatcher import ConversationSummaryDispatcherPort
from app.domain.ports.message_repository import MessageRepository
from app.infrastructure.llm.token_utils import count_tokens


class ManageConversationUseCase:
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        summary_dispatcher: ConversationSummaryDispatcherPort,
        summary_threshold: int = 10,
    ) -> None:
        self._conversation_repo = conversation_repo
        self._message_repo = message_repo
        self._summary_dispatcher = summary_dispatcher
        self._summary_threshold = summary_threshold

    async def create_conversation(
        self, workspace_id: UUID, user_id: UUID, title: str | None = None
    ) -> Conversation:
        now = datetime.now(UTC)
        return await self._conversation_repo.add(
            Conversation(
                id=uuid4(),
                workspace_id=workspace_id,
                user_id=user_id,
                title=title,
                summary=None,
                turn_count=0,
                is_deleted=False,
                created_at=now,
                updated_at=now,
            )
        )

    async def append_message(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
        citations: list[Citation] | None = None,
    ) -> Message:
        message = await self._message_repo.append(
            Message(
                id=uuid4(),
                conversation_id=conversation_id,
                role=role,
                content=content,
                citations=citations or [],
                token_count=count_tokens(content),
            )
        )

        # increment_turn_count raises ConversationNotFoundError itself if
        # conversation_id doesn't exist — deliberately let that propagate
        # rather than checking existence twice (once here, once there).
        new_turn_count = await self._conversation_repo.increment_turn_count(conversation_id)
        if new_turn_count % self._summary_threshold == 0:
            await self._summary_dispatcher.dispatch(conversation_id)

        return message

    async def get_context_window(
        self, conversation_id: UUID, max_turns: int
    ) -> tuple[str | None, list[Message]]:
        """Returns (summary, recent_messages) for agent state hydration —
        `summary` covers everything older than what `recent_messages`
        already carries verbatim, so a caller uses both together, never
        summary XOR full history beyond max_turns."""
        conversation = await self._conversation_repo.get_by_id(conversation_id)
        if conversation is None or conversation.is_deleted:
            raise ConversationNotFoundError(conversation_id)

        recent = await self._message_repo.list_recent(conversation_id, max_turns)
        return conversation.summary, recent
