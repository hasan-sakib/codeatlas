import itertools
from dataclasses import replace

from app.infrastructure.chunking.models import ChunkCandidate
from app.infrastructure.chunking.token_counter import count_tokens


class ChunkMerger:
    """Merges small adjacent chunks up to `merge_target_tokens` so
    retrieval doesn't return uselessly tiny fragments. Chunks only merge
    when they share both `file_path` and `symbol_kind` — this is what
    stops a class's trailing method chunk from merging into a following
    unrelated top-level function (different kind) as much as it stops
    cross-file merging.

    Known accepted gap: two *different* oversized classes whose adjacent
    trailing/leading pieces both happen to be kind="method" could
    theoretically merge across the class boundary. Not fixed for now —
    ChunkCandidate carries no parent-symbol identity to distinguish them,
    and this only arises when two adjacent classes are each individually
    oversized, a rarer compound case than the ones this module's design
    explicitly calls out.
    """

    def __init__(self, merge_target_tokens: int) -> None:
        self._merge_target_tokens = merge_target_tokens

    def merge(self, candidates: list[ChunkCandidate]) -> list[ChunkCandidate]:
        result: list[ChunkCandidate] = []
        for _file_path, group in itertools.groupby(candidates, key=lambda c: c.file_path):
            result.extend(self._merge_within_file(list(group)))
        return result

    def _merge_within_file(self, candidates: list[ChunkCandidate]) -> list[ChunkCandidate]:
        merged: list[ChunkCandidate] = []
        for candidate in candidates:
            combined = self._try_merge(merged[-1], candidate) if merged else None
            if combined is not None:
                merged[-1] = combined
            else:
                merged.append(candidate)
        return merged

    def _try_merge(self, a: ChunkCandidate, b: ChunkCandidate) -> ChunkCandidate | None:
        if a.symbol_kind != b.symbol_kind:
            return None

        joined_text = a.text + b.text
        joined_tokens = count_tokens(joined_text)
        if joined_tokens > self._merge_target_tokens:
            return None

        return replace(
            a,
            text=joined_text,
            token_count=joined_tokens,
            end_line=b.end_line,
            source_stage="merged",
        )
