import asyncio
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import git
import httpx

from app.domain.value_objects.clone_result import BlameEntry, ClonedRepo
from app.infrastructure.vcs.url_validator import (
    RepositoryUrlValidationError,
    resolve_and_check_ip,
    validate_repository_url,
)

_COMMIT_HEADER_RE = re.compile(r"^[0-9a-f]{40} \d+ \d+")


class GitPythonAdapter:
    """`GitPort` implementation backed by GitPython + a shelled-out
    `git blame`.

    See url_validator.py for why the private-IP/redirect checks live here
    (at connect time) rather than at repository-registration time.
    """

    def __init__(self, clone_timeout_seconds: float = 120.0, max_repo_size_mb: int = 500) -> None:
        self._clone_timeout_seconds = clone_timeout_seconds
        self._max_repo_size_bytes = max_repo_size_mb * 1024 * 1024

    async def clone(self, url: str, dest_dir: Path, *, shallow: bool = True) -> ClonedRepo:
        validate_repository_url(url)
        parsed = urlsplit(url)
        hostname = parsed.hostname
        assert hostname is not None  # guaranteed by validate_repository_url

        # Reject the original host up front so a malicious server can't
        # rely on us only ever checking the (attacker-controlled) redirect
        # target. Only re-check if a redirect actually changed the host —
        # re-checking the same host twice would be redundant.
        await resolve_and_check_ip(hostname)
        final_host = await self._follow_redirects_to_final_host(url, parsed.scheme, hostname)
        if final_host != hostname:
            await resolve_and_check_ip(final_host)

        dest_dir.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._clone_sync, url, dest_dir, shallow),
                timeout=self._clone_timeout_seconds,
            )
        except TimeoutError as exc:
            shutil.rmtree(dest_dir, ignore_errors=True)
            raise RepositoryUrlValidationError(
                f"Clone of {url!r} exceeded the {self._clone_timeout_seconds}s timeout"
            ) from exc

        size_bytes = await loop.run_in_executor(None, self._dir_size, dest_dir)
        if size_bytes > self._max_repo_size_bytes:
            shutil.rmtree(dest_dir, ignore_errors=True)
            max_mb = self._max_repo_size_bytes // (1024 * 1024)
            raise RepositoryUrlValidationError(
                f"Cloned repository exceeds the {max_mb}MB size limit"
            )

        repo = git.Repo(dest_dir)
        return ClonedRepo(
            local_path=dest_dir,
            commit_sha=repo.head.commit.hexsha,
            default_branch=repo.active_branch.name,
            size_bytes=size_bytes,
        )

    async def get_blame(
        self, repo_path: Path, file_path: str, start_line: int, end_line: int
    ) -> list[BlameEntry]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "blame",
            "-L",
            f"{start_line},{end_line}",
            "--line-porcelain",
            "--",
            file_path,
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git blame failed for {file_path}: {stderr.decode().strip()}")
        return _parse_line_porcelain(stdout.decode())

    async def _follow_redirects_to_final_host(self, url: str, scheme: str, hostname: str) -> str:
        if scheme != "https":
            return hostname  # ssh has no redirect concept

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                response = await client.head(url)
        except httpx.HTTPError:
            # Some git hosts reject HEAD on the smart-HTTP endpoint; a
            # failed pre-check here isn't itself a security signal — the
            # real clone below will surface a genuine connection failure.
            return hostname

        return urlsplit(str(response.url)).hostname or hostname

    def _clone_sync(self, url: str, dest_dir: Path, shallow: bool) -> None:
        git.Repo.clone_from(url, dest_dir, depth=1 if shallow else None, single_branch=True)

    def _dir_size(self, path: Path) -> int:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _parse_line_porcelain(output: str) -> list[BlameEntry]:
    entries: list[BlameEntry] = []
    commit_sha: str | None = None
    author: str | None = None
    author_time: int | None = None

    for line in output.splitlines():
        if _COMMIT_HEADER_RE.match(line):
            commit_sha = line.split(" ", 1)[0]
        elif line.startswith("author "):
            author = line[len("author ") :]
        elif line.startswith("author-time "):
            author_time = int(line.split(" ", 1)[1])
        elif line.startswith("\t"):
            if commit_sha is not None and author is not None and author_time is not None:
                entries.append(
                    BlameEntry(
                        author=author,
                        commit_sha=commit_sha,
                        committed_at=datetime.fromtimestamp(author_time, tz=UTC),
                    )
                )
            commit_sha = author = author_time = None

    return entries
