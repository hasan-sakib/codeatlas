from uuid import UUID


def reciprocal_rank_fusion(
    dense_ranked_ids: list[UUID],
    sparse_ranked_ids: list[UUID],
    k: int = 60,
) -> list[tuple[UUID, float]]:
    """Combines two rank-ordered id lists via `score(d) = sum(1 / (k + rank))`
    over every list `d` appears in (1-indexed rank) — an id present in both
    lists accumulates both contributions, boosting it above an id that only
    ranked well in one. An id absent from a list simply contributes nothing
    from that side; it isn't penalized beyond not getting that contribution.
    Returns every id that appeared in either input, sorted by descending
    fused score — callers slice to whatever top-K they need.
    """
    scores: dict[UUID, float] = {}
    for ranked_ids in (dense_ranked_ids, sparse_ranked_ids):
        for rank, chunk_id in enumerate(ranked_ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
