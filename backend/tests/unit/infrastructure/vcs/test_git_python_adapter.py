import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.infrastructure.vcs import git_python_adapter as gpa
from app.infrastructure.vcs.url_validator import RepositoryUrlValidationError


class _FakeCommit:
    hexsha = "abc123"


class _FakeBranch:
    name = "main"


class _FakeRepo:
    def __init__(self, path: Path) -> None:
        self.head = SimpleNamespace(commit=_FakeCommit())
        self.active_branch = _FakeBranch()


def _no_redirect_client_factory(final_url: str) -> type:
    class _FakeResponse:
        def __init__(self, url: str) -> None:
            self.url = url

    class _FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def head(self, url: str) -> _FakeResponse:
            return _FakeResponse(final_url)

    return _FakeAsyncClient


async def test_clone_validates_resolves_and_delegates_to_gitpython(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolved_hosts: list[str] = []

    async def fake_resolve(hostname: str) -> None:
        resolved_hosts.append(hostname)

    monkeypatch.setattr(gpa, "resolve_and_check_ip", fake_resolve)

    clone_calls = []

    def fake_clone_sync(
        self: gpa.GitPythonAdapter, url: str, dest_dir: Path, shallow: bool
    ) -> None:
        clone_calls.append((url, dest_dir, shallow))
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "file.txt").write_text("hello")

    monkeypatch.setattr(gpa.GitPythonAdapter, "_clone_sync", fake_clone_sync)
    monkeypatch.setattr(gpa.git, "Repo", _FakeRepo)

    adapter = gpa.GitPythonAdapter()
    dest_dir = tmp_path / "repo"
    result = await adapter.clone("ssh://git@github.com/org/repo.git", dest_dir)

    # ssh has no redirect concept, so only the original host is checked —
    # exactly once, not the redundant double-check a naive implementation
    # would do.
    assert resolved_hosts == ["github.com"]
    assert clone_calls == [("ssh://git@github.com/org/repo.git", dest_dir, True)]
    assert result.commit_sha == "abc123"
    assert result.default_branch == "main"
    assert result.local_path == dest_dir


async def test_clone_rejects_redirect_to_disallowed_host_without_cloning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_hosts: list[str] = []

    async def fake_resolve(hostname: str) -> None:
        checked_hosts.append(hostname)
        if hostname == "internal.evil.example":
            raise RepositoryUrlValidationError(f"disallowed: {hostname}")

    monkeypatch.setattr(gpa, "resolve_and_check_ip", fake_resolve)
    monkeypatch.setattr(
        gpa.httpx, "AsyncClient", _no_redirect_client_factory("https://internal.evil.example/x")
    )

    clone_calls = []
    monkeypatch.setattr(
        gpa.GitPythonAdapter,
        "_clone_sync",
        lambda self, url, dest_dir, shallow: clone_calls.append(url),
    )

    adapter = gpa.GitPythonAdapter()

    with pytest.raises(RepositoryUrlValidationError):
        await adapter.clone("https://github.com/org/repo.git", tmp_path / "repo")

    assert checked_hosts == ["github.com", "internal.evil.example"]
    assert clone_calls == []


async def test_clone_rejects_oversized_repo_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_resolve(hostname: str) -> None:
        return None

    monkeypatch.setattr(gpa, "resolve_and_check_ip", fake_resolve)

    def fake_clone_sync(
        self: gpa.GitPythonAdapter, url: str, dest_dir: Path, shallow: bool
    ) -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "big.bin").write_bytes(b"0" * 2048)

    monkeypatch.setattr(gpa.GitPythonAdapter, "_clone_sync", fake_clone_sync)

    adapter = gpa.GitPythonAdapter(max_repo_size_mb=0)
    dest_dir = tmp_path / "repo"

    with pytest.raises(RepositoryUrlValidationError):
        await adapter.clone("ssh://git@github.com/org/repo.git", dest_dir)

    assert not dest_dir.exists()


async def test_clone_times_out_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_resolve(hostname: str) -> None:
        return None

    monkeypatch.setattr(gpa, "resolve_and_check_ip", fake_resolve)

    def slow_clone_sync(
        self: gpa.GitPythonAdapter, url: str, dest_dir: Path, shallow: bool
    ) -> None:
        time.sleep(0.3)

    monkeypatch.setattr(gpa.GitPythonAdapter, "_clone_sync", slow_clone_sync)

    adapter = gpa.GitPythonAdapter(clone_timeout_seconds=0.05)
    dest_dir = tmp_path / "repo"

    with pytest.raises(RepositoryUrlValidationError):
        await adapter.clone("ssh://git@github.com/org/repo.git", dest_dir)

    assert not dest_dir.exists()


async def test_get_blame_parses_line_porcelain_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    porcelain_output = (
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 1 1 1\n"
        "author Amina Dev\n"
        "author-mail <amina@example.com>\n"
        "author-time 1700000000\n"
        "author-tz +0000\n"
        "summary Initial commit\n"
        "filename src/app.py\n"
        "\tprint('hello')\n"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 2 2 1\n"
        "author Marcus Dev\n"
        "author-mail <marcus@example.com>\n"
        "author-time 1700100000\n"
        "author-tz +0000\n"
        "summary Second commit\n"
        "filename src/app.py\n"
        "\tprint('world')\n"
    )

    class _FakeProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return porcelain_output.encode(), b""

    async def fake_subprocess_exec(*args: object, **kwargs: object) -> _FakeProcess:
        return _FakeProcess()

    monkeypatch.setattr(gpa.asyncio, "create_subprocess_exec", fake_subprocess_exec)

    adapter = gpa.GitPythonAdapter()
    entries = await adapter.get_blame(tmp_path, "src/app.py", 1, 2)

    assert len(entries) == 2
    assert entries[0].author == "Amina Dev"
    assert entries[0].commit_sha == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert entries[1].author == "Marcus Dev"
    assert entries[1].commit_sha == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


async def test_get_blame_raises_on_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeProcess:
        returncode = 128

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"fatal: no such path\n"

    async def fake_subprocess_exec(*args: object, **kwargs: object) -> _FakeProcess:
        return _FakeProcess()

    monkeypatch.setattr(gpa.asyncio, "create_subprocess_exec", fake_subprocess_exec)

    adapter = gpa.GitPythonAdapter()

    with pytest.raises(RuntimeError):
        await adapter.get_blame(tmp_path, "missing.py", 1, 2)
