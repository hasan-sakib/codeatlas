from uuid import uuid4

import pytest

from app.application.services.fusion import reciprocal_rank_fusion


def test_disjoint_id_sets_both_appear_with_positive_scores() -> None:
    a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()

    result = reciprocal_rank_fusion([a, b], [c, d], k=60)

    assert {chunk_id for chunk_id, _ in result} == {a, b, c, d}
    assert all(score > 0 for _, score in result)


def test_overlapping_id_boosts_above_single_list_hits() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()

    scores = dict(reciprocal_rank_fusion([a, b], [a, c], k=60))

    assert scores[a] == pytest.approx(1 / 61 + 1 / 61)
    assert scores[b] == pytest.approx(1 / 62)
    assert scores[c] == pytest.approx(1 / 62)
    assert scores[a] > scores[b]
    assert scores[a] > scores[c]


def test_empty_inputs_return_empty_list() -> None:
    assert reciprocal_rank_fusion([], []) == []


def test_results_sorted_descending_by_score() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()

    result = reciprocal_rank_fusion([a, b, c], [])

    assert [chunk_id for chunk_id, _ in result] == [a, b, c]
