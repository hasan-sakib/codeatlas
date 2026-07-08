from typing import Literal

from app.agent.state import AgentState, Intent
from app.core.config import AgentSettings


def _already_called(state: AgentState, tool_name: str) -> bool:
    return any(call["tool_name"] == tool_name for call in state.get("tool_calls", []))


def tool_router_node(state: AgentState, *, settings: AgentSettings) -> dict[str, object]:
    """Deliberately minimal v1 heuristic, not an LLM-driven decision:
    Ollama's qwen3:4b does support real tool-calling (confirmed via
    `ollama show qwen3:4b` -> capabilities include "tools"), but wiring
    that through would mean extending Module 14's LLMPort with a new
    structured-output method — real, separate scope, not something to
    fold into this module silently. The one case handled for real:
    a debugging question with retrieved context gets exactly one
    get_git_blame call, since "who last touched this and when" is
    concretely useful for a bug report and doesn't require guessing at
    LLM-driven argument extraction. get_file and run_search are fully
    implemented and tested (see app/agent/tools/) but not yet reachable
    from this heuristic — wired and ready for a smarter router.
    """

    if len(state.get("tool_calls", [])) >= settings.max_tool_calls:
        return {"next_tool": None}

    if (
        state.get("intent") == Intent.DEBUGGING
        and state.get("reranked_chunks")
        and not _already_called(state, "get_git_blame")
    ):
        return {"next_tool": "get_git_blame"}

    return {"next_tool": None}


def tool_router_edge(state: AgentState) -> Literal["call_tool", "generate_answer"]:
    return "call_tool" if state.get("next_tool") else "generate_answer"
