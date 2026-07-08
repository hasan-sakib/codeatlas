import operator
from enum import Enum
from typing import Annotated, TypedDict
from uuid import UUID

from app.domain.entities.message import Citation, Message
from app.domain.value_objects.ranked_chunk import RankedChunk


class Intent(str, Enum):
    CODE_QA = "code_qa"
    DEBUGGING = "debugging"
    ARCHITECTURE_EXPLAIN = "architecture_explain"
    DOC_GENERATION = "doc_generation"
    GENERAL_CHAT = "general_chat"


class ToolCallRecord(TypedDict):
    tool_name: str
    arguments: dict[str, str]
    result: str | None
    error: str | None


class AgentState(TypedDict, total=False):
    # --- input: set by the caller before invoking the graph. This
    # module doesn't hydrate conversation history itself (that's
    # ManageConversationUseCase.get_context_window, called by whichever
    # future use case wires HTTP -> conversation -> agent) — the graph
    # takes messages/conversation_summary as already-resolved input. ---
    conversation_id: UUID
    workspace_id: UUID
    user_id: UUID
    query: str
    embedding_version: str
    conversation_summary: str | None
    messages: list[Message]

    # --- populated during graph execution ---
    rewritten_query: str | None
    intent: Intent | None
    retrieved_chunks: list[RankedChunk]
    reranked_chunks: list[RankedChunk]
    retrieval_attempts: int
    needs_more_context: bool
    next_tool: str | None
    tool_calls: Annotated[list[ToolCallRecord], operator.add]
    # The exact chunks placed into the generate_answer prompt (a
    # settings.context_chunk_count-sized slice of reranked_chunks) — set
    # by generate_answer_node and consumed by cite_sources_node, so
    # citations always match what the LLM actually saw rather than
    # re-deriving (and risking drift from) the same slice twice.
    context_chunks: list[RankedChunk]
    citations: list[Citation]
    final_answer: str | None
    error: str | None
