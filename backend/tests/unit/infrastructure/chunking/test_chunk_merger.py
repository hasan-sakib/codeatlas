from app.infrastructure.chunking.chunk_merger import ChunkMerger
from app.infrastructure.chunking.models import ChunkCandidate
from app.infrastructure.chunking.token_counter import count_tokens


def _candidate(
    text: str, kind: str, start: int, end: int, file_path: str = "app.py", stage: str = "ast"
) -> ChunkCandidate:
    return ChunkCandidate(
        text=text,
        token_count=count_tokens(text),
        file_path=file_path,
        language="python",
        symbol_kind=kind,  # type: ignore[arg-type]
        symbol_name=None,
        start_line=start,
        end_line=end,
        source_stage=stage,  # type: ignore[arg-type]
    )


def test_merges_consecutive_small_same_kind_chunks_under_budget() -> None:
    chunks = [
        _candidate("def a(): pass\n", "function", 1, 1),
        _candidate("def b(): pass\n", "function", 3, 3),
        _candidate("def c(): pass\n", "function", 5, 5),
    ]

    merged = ChunkMerger(merge_target_tokens=200).merge(chunks)

    assert len(merged) == 1
    assert merged[0].source_stage == "merged"
    assert merged[0].start_line == 1
    assert merged[0].end_line == 5
    assert merged[0].text == "def a(): pass\ndef b(): pass\ndef c(): pass\n"


def test_does_not_merge_a_chunk_that_would_exceed_the_budget() -> None:
    small = "def a(): pass\n"
    budget = count_tokens(small * 2)
    chunks = [
        _candidate(small, "function", 1, 1),
        _candidate(small, "function", 2, 2),
        _candidate(small, "function", 3, 3),
    ]

    merged = ChunkMerger(merge_target_tokens=budget).merge(chunks)

    assert len(merged) == 2
    assert merged[0].source_stage == "merged"
    assert merged[1].source_stage == "ast"


def test_never_merges_across_a_class_boundary_into_an_unrelated_function() -> None:
    chunks = [
        _candidate("    def method(self): pass\n", "method", 1, 1),
        _candidate("def top(): pass\n", "function", 3, 3),
    ]

    merged = ChunkMerger(merge_target_tokens=1000).merge(chunks)

    assert len(merged) == 2


def test_never_merges_across_file_boundaries() -> None:
    chunks = [
        _candidate("def a(): pass\n", "function", 1, 1, file_path="a.py"),
        _candidate("def b(): pass\n", "function", 1, 1, file_path="b.py"),
    ]

    merged = ChunkMerger(merge_target_tokens=1000).merge(chunks)

    assert len(merged) == 2
    assert merged[0].file_path == "a.py"
    assert merged[1].file_path == "b.py"
