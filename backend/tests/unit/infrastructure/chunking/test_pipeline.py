from datetime import UTC, datetime
from pathlib import Path

from app.domain.value_objects.clone_result import BlameEntry, ClonedRepo
from app.infrastructure.chunking.pipeline import chunk_file
from app.infrastructure.parsing.metadata_extractor import MetadataExtractor
from app.infrastructure.parsing.parsers.python_parser import PythonParser


class _FakeGitPort:
    async def clone(self, url: str, dest_dir: Path, *, shallow: bool = True) -> ClonedRepo:
        raise NotImplementedError

    async def get_blame(
        self, repo_path: Path, file_path: str, start_line: int, end_line: int
    ) -> list[BlameEntry]:
        return [
            BlameEntry(
                author="Amina Dev",
                commit_sha="abc123",
                committed_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]


async def test_chunk_file_on_real_world_file_respects_hard_invariants() -> None:
    real_file = (
        Path(__file__).resolve().parents[4]
        / "app"
        / "infrastructure"
        / "vcs"
        / "git_python_adapter.py"
    )
    source = real_file.read_bytes()
    lines = source.decode().splitlines()

    parser = PythonParser()
    parsed = parser.parse(source)
    metadata = await MetadataExtractor(_FakeGitPort()).extract(
        parsed, Path("/repo"), "git_python_adapter.py"
    )

    max_tokens, min_tokens, merge_target = 512, 64, 256
    candidates = chunk_file(
        parsed,
        metadata,
        "git_python_adapter.py",
        max_chunk_tokens=max_tokens,
        min_chunk_tokens=min_tokens,
        merge_target_tokens=merge_target,
    )

    assert candidates

    # Hard guarantee: AstChunker never emits a piece over the ceiling.
    assert all(c.token_count <= max_tokens for c in candidates)

    # Hard guarantee: full, non-overlapping coverage — any gap between
    # consecutive candidates is blank lines only, never dropped content.
    ordered = sorted(candidates, key=lambda c: c.start_line)
    prev_end = 0
    for candidate in ordered:
        assert candidate.start_line > prev_end
        gap_lines = lines[prev_end : candidate.start_line - 1]
        assert all(not line.strip() for line in gap_lines)
        prev_end = candidate.end_line
    assert prev_end == len(lines)

    # min_chunk_tokens is best-effort, not absolute: a small piece
    # adjacent to an already-near-max-size neighbor has no room to merge
    # without breaking the max_chunk_tokens ceiling (merging would need
    # to exceed merge_target_tokens, or even max_chunk_tokens itself).
    # Regression-pinned against the real file as it stands today rather
    # than asserted as a strict zero — see docs/modules/chunking_engine.md
    # for the empirical finding behind this.
    below_min = sorted(c.token_count for c in candidates if c.token_count < min_tokens)
    assert below_min == [51, 60]
