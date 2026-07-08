from uuid import uuid4

import pytest

from app.domain.value_objects.ranked_chunk import RankedChunk
from app.infrastructure.reranker.cross_encoder_reranker import CrossEncoderReranker, _truncate


def _make_chunk(text: str, score: float = 0.5) -> RankedChunk:
    return RankedChunk(
        chunk_id=uuid4(),
        file_path="a.py",
        start_line=1,
        end_line=2,
        symbol_name="foo",
        score=score,
        source="fused",
        text=text,
    )


async def test_score_reorders_chunks_by_predicted_score_descending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk_low = _make_chunk("low relevance", score=0.9)  # high fused score, low rerank score
    chunk_high = _make_chunk("high relevance", score=0.1)  # low fused score, high rerank score

    def fake_predict_batch(self: CrossEncoderReranker, pairs: list[tuple[str, str]]) -> list[float]:
        return [0.1, 0.9]  # matches [chunk_low, chunk_high] input order

    monkeypatch.setattr(CrossEncoderReranker, "_predict_batch", fake_predict_batch)
    reranker = CrossEncoderReranker(model_name="fake-model")

    results = await reranker.score("query", [chunk_low, chunk_high])

    assert [r.chunk_id for r in results] == [chunk_high.chunk_id, chunk_low.chunk_id]
    assert all(r.source == "reranked" for r in results)
    assert results[0].score == 0.9
    assert results[1].score == 0.1


async def test_score_returns_full_reordered_list_without_slicing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [_make_chunk(f"chunk {i}") for i in range(5)]
    monkeypatch.setattr(
        CrossEncoderReranker, "_predict_batch", lambda self, pairs: [float(i) for i in range(5)]
    )
    reranker = CrossEncoderReranker(model_name="fake-model")

    results = await reranker.score("query", chunks)

    assert len(results) == 5  # no N-slicing here — that's RetrievalService's job


async def test_score_with_empty_chunks_returns_empty_without_predicting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_predict_batch(self: CrossEncoderReranker, pairs: list[tuple[str, str]]) -> list[float]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(CrossEncoderReranker, "_predict_batch", fake_predict_batch)
    reranker = CrossEncoderReranker(model_name="fake-model")

    results = await reranker.score("query", [])

    assert results == []
    assert called is False


async def test_score_truncates_long_chunk_text_but_keeps_the_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_text = "x" * 10_000
    chunk = _make_chunk(long_text)
    captured_pairs: list[tuple[str, str]] = []

    def fake_predict_batch(self: CrossEncoderReranker, pairs: list[tuple[str, str]]) -> list[float]:
        captured_pairs.extend(pairs)
        return [0.5]

    monkeypatch.setattr(CrossEncoderReranker, "_predict_batch", fake_predict_batch)
    reranker = CrossEncoderReranker(model_name="fake-model", max_length=100)

    results = await reranker.score("query", [chunk])

    assert len(results) == 1  # chunk survives, just with truncated text sent to the model
    assert len(captured_pairs[0][1]) < len(long_text)
    assert captured_pairs[0][0] == "query"  # the query itself is never truncated


async def test_score_fails_open_and_returns_input_unchanged_when_predict_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk_a, chunk_b = _make_chunk("a"), _make_chunk("b")

    def raising_predict_batch(
        self: CrossEncoderReranker, pairs: list[tuple[str, str]]
    ) -> list[float]:
        raise RuntimeError("model exploded")

    monkeypatch.setattr(CrossEncoderReranker, "_predict_batch", raising_predict_batch)
    reranker = CrossEncoderReranker(model_name="fake-model", fail_open=True)

    results = await reranker.score("query", [chunk_a, chunk_b])

    assert results == [chunk_a, chunk_b]  # unchanged, original order
    assert results[0].source == "fused"  # never retagged "reranked"


async def test_score_reraises_when_fail_open_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    def raising_predict_batch(
        self: CrossEncoderReranker, pairs: list[tuple[str, str]]
    ) -> list[float]:
        raise RuntimeError("model exploded")

    monkeypatch.setattr(CrossEncoderReranker, "_predict_batch", raising_predict_batch)
    reranker = CrossEncoderReranker(model_name="fake-model", fail_open=False)

    with pytest.raises(RuntimeError, match="model exploded"):
        await reranker.score("query", [_make_chunk("a")])


def test_truncate_leaves_short_text_unchanged() -> None:
    assert _truncate("short", max_length=100) == "short"


def test_truncate_shortens_long_text() -> None:
    long_text = "x" * 10_000
    result = _truncate(long_text, max_length=10)
    assert result == "x" * 40  # 10 tokens * 4 chars/token heuristic
