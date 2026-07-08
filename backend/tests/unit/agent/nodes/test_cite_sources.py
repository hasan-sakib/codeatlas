from app.agent.nodes.cite_sources import cite_sources_node
from app.domain.entities.message import Citation
from tests.unit.agent.fakes import make_chunk


def test_cite_sources_builds_from_context_chunks_not_reranked_chunks() -> None:
    context_chunk = make_chunk(file_path="used.py")
    unused_chunk = make_chunk(file_path="not_used.py")
    result = cite_sources_node(
        {"context_chunks": [context_chunk], "reranked_chunks": [context_chunk, unused_chunk]}
    )
    (citation,) = result["citations"]
    assert citation == Citation(
        chunk_id=context_chunk.chunk_id,
        file_path="used.py",
        start_line=context_chunk.start_line,
        end_line=context_chunk.end_line,
        score=context_chunk.score,
    )


def test_cite_sources_empty_when_no_context_chunks() -> None:
    assert cite_sources_node({"context_chunks": []}) == {"citations": []}


def test_cite_sources_defaults_to_empty_when_field_absent() -> None:
    assert cite_sources_node({}) == {"citations": []}
