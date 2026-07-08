from uuid import UUID

from app.domain.exceptions import ConversationNotFoundError
from app.domain.ports.conversation_repository import ConversationRepository
from app.domain.ports.llm_port import LLMPort
from app.domain.ports.message_repository import MessageRepository
from app.infrastructure.llm.prompt_renderer import PromptRenderer

# Generous relative to a typical summary's actual length, but summaries
# occasionally need to preserve several file paths/symbol names verbatim
# (per summarize.jinja's instruction) — 512 leaves headroom for that
# without risking the truncation failure mode Module 14 found for
# thinking-heavy responses at tighter budgets.
_SUMMARY_MAX_TOKENS = 512


class SummarizeConversationUseCase:
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        llm_port: LLMPort,
        prompt_renderer: PromptRenderer,
        context_turns: int = 20,
    ) -> None:
        self._conversation_repo = conversation_repo
        self._message_repo = message_repo
        self._llm_port = llm_port
        self._prompt_renderer = prompt_renderer
        self._context_turns = context_turns

    async def execute(self, conversation_id: UUID) -> str:
        conversation = await self._conversation_repo.get_by_id(conversation_id)
        if conversation is None or conversation.is_deleted:
            raise ConversationNotFoundError(conversation_id)

        messages = await self._message_repo.list_recent(conversation_id, self._context_turns)
        prompt = self._prompt_renderer.render(
            "summarize.jinja",
            messages=[{"role": m.role.value, "content": m.content} for m in messages],
            existing_summary=conversation.summary,
        )

        result = await self._llm_port.complete(
            prompt, max_tokens=_SUMMARY_MAX_TOKENS, temperature=0.2
        )
        await self._conversation_repo.update_summary(conversation_id, result.text)
        return result.text
