from app.infrastructure.llm.token_utils import count_tokens, truncate_to_budget


def test_count_tokens_empty_string_is_zero() -> None:
    assert count_tokens("") == 0


def test_count_tokens_scales_monotonically_with_length() -> None:
    short = count_tokens("hello")
    longer = count_tokens("hello world, this is a longer sentence with more words")
    assert longer > short


def test_count_tokens_matches_hand_verified_count_for_fixed_string() -> None:
    # Regression pin against tokenizer/version drift — verified by
    # actually running the real Qwen/Qwen3-4B tokenizer.
    text = "Hello world, this is a test of the Qwen3 tokenizer."
    assert count_tokens(text) == 14


def test_truncate_to_budget_under_budget_passes_through_unchanged() -> None:
    segments = ["short one", "short two", "short three"]
    result = truncate_to_budget(segments, max_tokens=1000, keep="newest")
    assert result == segments


def test_truncate_to_budget_newest_drops_oldest_first() -> None:
    # Oldest-first input order (conversation turns) — "newest" keeps the
    # tail, dropping from the front once the budget is exceeded.
    segments = ["a" * 40, "b" * 40, "c" * 40]  # each ~10 tokens of filler
    budget = count_tokens(segments[1]) + count_tokens(segments[2])
    result = truncate_to_budget(segments, max_tokens=budget, keep="newest")
    assert result == [segments[1], segments[2]]


def test_truncate_to_budget_highest_relevance_drops_from_the_back() -> None:
    # Most-relevant-first input order (reranked chunks) —
    # "highest_relevance" keeps the head, dropping from the back.
    segments = ["a" * 40, "b" * 40, "c" * 40]
    budget = count_tokens(segments[0]) + count_tokens(segments[1])
    result = truncate_to_budget(segments, max_tokens=budget, keep="highest_relevance")
    assert result == [segments[0], segments[1]]


def test_truncate_to_budget_zero_budget_drops_everything() -> None:
    assert truncate_to_budget(["anything"], max_tokens=0, keep="newest") == []


def test_truncate_to_budget_preserves_relative_order_of_kept_segments() -> None:
    segments = [f"segment-{i} " + "x" * 20 for i in range(5)]
    result = truncate_to_budget(segments, max_tokens=1000, keep="newest")
    assert result == segments
