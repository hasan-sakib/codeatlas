from typing import Literal

from app.agent.state import AgentState, Intent
from app.core.config import AgentSettings
from app.domain.exceptions import LLMUnavailableError
from app.domain.ports.llm_port import LLMPort
from app.infrastructure.llm.prompt_renderer import PromptRenderer

_VALID_INTENTS = tuple(intent.value for intent in Intent)


def _parse_intent(text: str) -> Intent:
    lowered = text.strip().lower()
    for value in _VALID_INTENTS:
        # Substring match, not exact equality — Qwen3's thinking mode
        # occasionally wraps the answer in extra words ("Category:
        # code_qa.") despite the prompt asking for just the label,
        # verified against the real model during development.
        if value in lowered:
            return Intent(value)
    return Intent.CODE_QA  # ambiguous defaults to "needs retrieval", the safer failure mode


async def classify_intent_node(
    state: AgentState,
    *,
    llm_port: LLMPort,
    prompt_renderer: PromptRenderer,
    settings: AgentSettings,
) -> dict[str, object]:
    prompt = prompt_renderer.render("classify_intent.jinja", query=state["query"])
    try:
        result = await llm_port.complete(
            prompt, max_tokens=settings.classify_intent_max_tokens, temperature=0.0
        )
    except LLMUnavailableError as exc:
        return {"error": str(exc)}

    return {"intent": _parse_intent(result.text)}


def classify_intent_edge(
    state: AgentState,
) -> Literal["error_handler", "rewrite_query", "generate_answer"]:
    if state.get("error"):
        return "error_handler"
    return "generate_answer" if state.get("intent") == Intent.GENERAL_CHAT else "rewrite_query"
