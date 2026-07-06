from pathlib import Path
from typing import Protocol

from app.domain.value_objects.clone_result import BlameEntry, ClonedRepo


class GitPort(Protocol):
    async def clone(self, url: str, dest_dir: Path, *, shallow: bool = True) -> ClonedRepo:
        """Clone `url` into `dest_dir`.

        Performs the authoritative SSRF check (scheme + DNS resolution +
        private/loopback/link-local IP rejection, re-checked after any
        redirect) immediately before connecting — not earlier, since the
        result of an earlier check can go stale by the time this runs.
        """
        ...

    async def get_blame(
        self, repo_path: Path, file_path: str, start_line: int, end_line: int
    ) -> list[BlameEntry]: ...
