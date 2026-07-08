from uuid import uuid4

from app.agent.nodes.retrieve_context import retrieve_context_node
from app.core.config import AgentSettings
from app.domain.value_objects.retrieval_query import RetrievalQuery
from tests.unit.agent.fakes import FakeRetrievalService, make_chunk


async def test_retrieve_context_first_attempt_uses_base_k() -> None:
    service = FakeRetrievalService(results=[make_chunk()])
    result = await retrieve_context_node(
        {
            "workspace_id": uuid4(),
            "query": "q",
            "embedding_version": "v1",
            "retrieval_attempts": 0,
        },
        retrieval_service=service,
        settings=AgentSettings(retry_k_multiplier=2),
    )
    assert result["retrieval_attempts"] == 1
    assert len(result["retrieved_chunks"]) == 1
    query: RetrievalQuery = service.calls[0]
    assert query.k1 == 40
    assert query.k2 == 50


async def test_retrieve_context_widens_k_on_retry() -> None:
    service = FakeRetrievalService(results=[])
    result = await retrieve_context_node(
        {
            "workspace_id": uuid4(),
            "query": "q",
            "embedding_version": "v1",
            "retrieval_attempts": 1,
        },
        retrieval_service=service,
        settings=AgentSettings(retry_k_multiplier=2),
    )
    assert result["retrieval_attempts"] == 2
    query: RetrievalQuery = service.calls[0]
    assert query.k1 == 80
    assert query.k2 == 100


async def test_retrieve_context_prefers_rewritten_query() -> None:
    service = FakeRetrievalService()
    await retrieve_context_node(
        {
            "workspace_id": uuid4(),
            "query": "original",
            "rewritten_query": "rewritten",
            "embedding_version": "v1",
            "retrieval_attempts": 0,
        },
        retrieval_service=service,
        settings=AgentSettings(),
    )
    query: RetrievalQuery = service.calls[0]
    assert query.query_text == "rewritten"


async def test_retrieve_context_sets_error_on_exception() -> None:
    service = FakeRetrievalService(raise_exc=RuntimeError("db down"))
    result = await retrieve_context_node(
        {
            "workspace_id": uuid4(),
            "query": "q",
            "embedding_version": "v1",
            "retrieval_attempts": 0,
        },
        retrieval_service=service,
        settings=AgentSettings(),
    )
    assert result == {"error": "db down"}
