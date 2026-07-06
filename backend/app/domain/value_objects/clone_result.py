from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ClonedRepo:
    local_path: Path
    commit_sha: str
    default_branch: str
    size_bytes: int


@dataclass(frozen=True)
class BlameEntry:
    author: str
    commit_sha: str
    committed_at: datetime
