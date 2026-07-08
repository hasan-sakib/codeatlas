from app.agent.state import AgentState
from app.application.services.retrieval_service import RetrievalService
from app.core.config import AgentSettings
from app.domain.value_objects.retrieval_query import RetrievalQuery

_BASE_K1 = 40
_BASE_K2 = 50


async def retrieve_context_node(
    state: AgentState, *, retrieval_service: RetrievalService, settings: AgentSettings
) -> dict[str, object]:
    attempts = state.get("retrieval_attempts", 0)
    # Widen on each retry past the first attempt (assess_sufficiency's
    # "insufficient, try again" path) — owned here, not by the caller,
    # per the design's explicit note that retrieve_context_node reads
    # its own attempt count to decide how much to widen.
    widen = settings.retry_k_multiplier**attempts
    query = RetrievalQuery(
        workspace_id=state["workspace_id"],
        query_text=state.get("rewritten_query") or state["query"],
        embedding_version=state["embedding_version"],
        k1=_BASE_K1 * widen,
        k2=_BASE_K2 * widen,
    )
    try:
        # Broad catch is deliberate: retrieval/DB/vector-store failures
        # have no single well-typed exception here (unlike the LLM's own
        # LLMUnavailableError).
        chunks = await retrieval_service.retrieve_without_rerank(query)
    except Exception as exc:
        return {"error": str(exc)}

    return {"retrieved_chunks": chunks, "retrieval_attempts": attempts + 1}
