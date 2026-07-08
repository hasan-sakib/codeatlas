from app.agent.state import AgentState
from app.domain.ports.reranker_port import RerankerPort


async def rerank_node(state: AgentState, *, reranker_port: RerankerPort) -> dict[str, object]:
    chunks = state.get("retrieved_chunks", [])
    if not chunks:
        return {"reranked_chunks": []}

    # No try/except here: RerankerSettings.fail_open defaults to True, so
    # in the deployed default configuration score() already returns
    # chunks unchanged on a model failure rather than raising (Module
    # 12). If an operator sets fail_open=False, a rerank failure
    # propagating as a graph error is the intended, requested behavior
    # for that configuration, not an oversight.
    reranked = await reranker_port.score(state.get("rewritten_query") or state["query"], chunks)
    return {"reranked_chunks": reranked}
