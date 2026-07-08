from app.agent.nodes.rerank import rerank_node
from tests.unit.agent.fakes import FakeRerankerPort, make_chunk


async def test_rerank_skips_call_when_no_retrieved_chunks() -> None:
    reranker = FakeRerankerPort()
    result = await rerank_node({"retrieved_chunks": [], "query": "q"}, reranker_port=reranker)
    assert result == {"reranked_chunks": []}
    assert reranker.calls == []


async def test_rerank_calls_reranker_with_rewritten_query_when_present() -> None:
    chunk = make_chunk()
    reordered = [chunk]
    reranker = FakeRerankerPort(reordered=reordered)
    result = await rerank_node(
        {"retrieved_chunks": [chunk], "query": "original", "rewritten_query": "rewritten"},
        reranker_port=reranker,
    )
    assert result == {"reranked_chunks": reordered}
    assert reranker.calls == [("rewritten", [chunk])]


async def test_rerank_falls_back_to_query_when_no_rewritten_query() -> None:
    chunk = make_chunk()
    reranker = FakeRerankerPort()
    await rerank_node({"retrieved_chunks": [chunk], "query": "original"}, reranker_port=reranker)
    assert reranker.calls[0][0] == "original"
