import pytest

from app.agent.nodes.assess_sufficiency import assess_sufficiency_edge, assess_sufficiency_node
from app.core.config import AgentSettings
from tests.unit.agent.fakes import make_chunk


def test_assess_sufficiency_node_true_when_no_reranked_chunks() -> None:
    assert assess_sufficiency_node({"reranked_chunks": []}) == {"needs_more_context": True}


def test_assess_sufficiency_node_false_when_chunks_present() -> None:
    assert assess_sufficiency_node({"reranked_chunks": [make_chunk()]}) == {
        "needs_more_context": False
    }


@pytest.mark.parametrize(
    ("needs_more_context", "attempts", "max_attempts", "expected"),
    [
        (True, 0, 2, "retrieve_context"),
        (True, 1, 2, "retrieve_context"),
        (True, 2, 2, "tool_router"),  # exhausted retry budget, proceed anyway
        (False, 0, 2, "tool_router"),
    ],
)
def test_assess_sufficiency_edge(
    needs_more_context: bool, attempts: int, max_attempts: int, expected: str
) -> None:
    state = {"needs_more_context": needs_more_context, "retrieval_attempts": attempts}
    settings = AgentSettings(max_retrieval_attempts=max_attempts)
    assert assess_sufficiency_edge(state, settings=settings) == expected  # type: ignore[arg-type]
