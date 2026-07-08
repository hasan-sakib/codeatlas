from collections.abc import Callable

import structlog
from langgraph.config import get_stream_writer

from app.agent.state import AgentState, Intent
from app.core.config import AgentSettings
from app.domain.exceptions import LLMUnavailableError
from app.domain.ports.llm_port import LLMPort
from app.domain.value_objects.ranked_chunk import RankedChunk
from app.infrastructure.llm.prompt_renderer import PromptRenderer

logger = structlog.get_logger(__name__)

_EMPTY_ANSWER_FALLBACK = (
    "I wasn't able to produce an answer for that within the model's response budget. "
    "Try rephrasing your question more narrowly."
)


def _get_writer() -> Callable[[object], None]:
    # get_stream_writer() raises RuntimeError outside a real LangGraph
    # `.astream(...)` execution context — verified directly. Falling
    # back to a no-op keeps this node directly unit-testable (calling it
    # with a plain state dict and fake ports, no compiled graph needed),
    # matching the design's own stated testing approach for nodes, while
    # still emitting real per-token events when actually run in a graph.
    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda _: None


def _render_prompt(
    state: AgentState, prompt_renderer: PromptRenderer, context_chunks: list[RankedChunk]
) -> str:
    history = [{"role": m.role.value, "content": m.content} for m in state.get("messages", [])]
    query = state.get("rewritten_query") or state["query"]

    if state.get("intent") == Intent.GENERAL_CHAT:
        # A greeting/thanks has no retrieved context and shouldn't be
        # forced through rag_answer.jinja's "refuse without context"
        # framing — verified empirically: doing so produced "The context
        # does not contain enough information to answer" for "thanks for
        # the help!", which is a real bug, not an edge case worth
        # tolerating.
        return prompt_renderer.render("general_chat.jinja", query=query, history=history)

    chunk_dicts = [
        {
            "file_path": c.file_path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "text": c.text or "",
        }
        for c in context_chunks
    ]
    tool_outputs = [
        call["result"]
        for call in state.get("tool_calls", [])
        if call.get("result") and not call.get("error")
    ]
    return prompt_renderer.render(
        "rag_answer.jinja",
        query=query,
        chunks=chunk_dicts,
        history=history,
        conversation_summary=state.get("conversation_summary"),
        tool_outputs=tool_outputs,
    )


async def generate_answer_node(
    state: AgentState,
    *,
    llm_port: LLMPort,
    prompt_renderer: PromptRenderer,
    settings: AgentSettings,
) -> dict[str, object]:
    writer = _get_writer()
    is_general_chat = state.get("intent") == Intent.GENERAL_CHAT
    context_chunks: list[RankedChunk] = (
        [] if is_general_chat else state.get("reranked_chunks", [])[: settings.context_chunk_count]
    )

    prompt = _render_prompt(state, prompt_renderer, context_chunks)

    text_parts: list[str] = []
    try:
        async for token in llm_port.stream_complete(
            prompt, max_tokens=settings.generate_answer_max_tokens
        ):
            writer({"type": "token", "text": token})
            text_parts.append(token)
    except LLMUnavailableError as exc:
        return {"error": str(exc)}

    if not text_parts:
        # Verified directly against the real model: Qwen3's thinking
        # phase can consume the entire max_tokens budget before any
        # answer text appears, especially with the fuller context a real
        # RAG prompt carries — finish_reason="length", response="". This
        # is an honest "the model produced nothing", not a system
        # failure, so it doesn't route through error_handler.
        logger.warning(
            "agent.generate_answer.empty_response", max_tokens=settings.generate_answer_max_tokens
        )
        return {"final_answer": _EMPTY_ANSWER_FALLBACK, "context_chunks": context_chunks}

    return {"final_answer": "".join(text_parts), "context_chunks": context_chunks}
