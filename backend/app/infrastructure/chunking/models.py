from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ChunkCandidate:
    """The hand-off contract to Module 9 (embedding) and eventually
    persistence (which adds a UUID id, workspace_id, repository_id,
    embedding_version on top of this).
    """

    text: str
    token_count: int
    file_path: str
    language: str
    symbol_kind: Literal["function", "class", "method", "module", "markdown_section", "docstring"]
    symbol_name: str | None
    start_line: int
    end_line: int
    source_stage: Literal["ast", "semantic", "merged"]
