from typing import Literal

from app.agent.state import AgentState
from app.core.config import AgentSettings


def assess_sufficiency_node(state: AgentState) -> dict[str, object]:
    # A single, honest signal: are there any reranked candidates at all.
    # A relevance-score threshold was considered (per the design's own
    # language) but deliberately not added — bge-reranker-base's raw
    # scores aren't a calibrated, bounded quantity (verified empirically
    # in Module 12: 0.044 vs 0.000037 for a relevant/irrelevant pair,
    # not a [0,1] probability), so any fixed cutoff here would be an
    # arbitrary number dressed up as a principled threshold.
    return {"needs_more_context": len(state.get("reranked_chunks", [])) == 0}


def assess_sufficiency_edge(
    state: AgentState, *, settings: AgentSettings
) -> Literal["retrieve_context", "tool_router"]:
    insufficient = state.get("needs_more_context", False)
    attempts = state.get("retrieval_attempts", 0)
    if insufficient and attempts < settings.max_retrieval_attempts:
        return "retrieve_context"
    return "tool_router"
