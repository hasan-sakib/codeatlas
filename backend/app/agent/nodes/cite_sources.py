from app.agent.state import AgentState
from app.domain.entities.message import Citation


def cite_sources_node(state: AgentState) -> dict[str, object]:
    # Built from context_chunks (exactly what generate_answer placed in
    # the prompt), never parsed from the LLM's free-form answer text —
    # a citation can't reference something the model didn't actually
    # see, and the model can't hallucinate one that isn't in this list.
    chunks = state.get("context_chunks", [])
    citations = [
        Citation(
            chunk_id=c.chunk_id,
            file_path=c.file_path,
            start_line=c.start_line,
            end_line=c.end_line,
            score=c.score,
        )
        for c in chunks
    ]
    return {"citations": citations}
