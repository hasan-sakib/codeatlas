from app.agent.state import AgentState
from app.core.config import AgentSettings
from app.domain.exceptions import LLMUnavailableError
from app.domain.ports.llm_port import LLMPort
from app.infrastructure.llm.prompt_renderer import PromptRenderer


async def rewrite_query_node(
    state: AgentState,
    *,
    llm_port: LLMPort,
    prompt_renderer: PromptRenderer,
    settings: AgentSettings,
) -> dict[str, object]:
    history = [{"role": m.role.value, "content": m.content} for m in state.get("messages", [])]
    if not history:
        # Nothing to resolve pronouns/references against on a first
        # turn — rewriting could only ever return the same text, so
        # skip the LLM call entirely.
        return {"rewritten_query": state["query"]}

    prompt = prompt_renderer.render("query_rewrite.jinja", query=state["query"], history=history)
    try:
        result = await llm_port.complete(
            prompt, max_tokens=settings.rewrite_query_max_tokens, temperature=0.0
        )
    except LLMUnavailableError as exc:
        return {"error": str(exc)}

    return {"rewritten_query": result.text.strip() or state["query"]}
