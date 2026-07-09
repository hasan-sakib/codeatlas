from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.application.use_cases.indexing.run_indexing_pipeline import RunIndexingPipelineUseCase
from app.domain.entities.indexing_job import IndexingJob, IndexingJobStatus
from app.domain.entities.repository import Repository, RepositorySourceType, RepositoryStatus
from app.domain.value_objects.clone_result import ClonedRepo
from tests.unit.application.use_cases.indexing.fakes import (
    FakeChunkRepository,
    FakeEmbeddingPort,
    FakeFileRepository,
    FakeGitPort,
    FakeIndexingJobRepository,
    FakeRepositoryRepository,
    FakeVectorStorePort,
)

_MAX_CHUNK_TOKENS = 512
_MIN_CHUNK_TOKENS = 64
_MERGE_TARGET_TOKENS = 256
_MAX_FILE_SIZE_BYTES = 1_000_000
_EXCLUDED_DIR_NAMES = frozenset({".git", "node_modules"})


def _write_fixture_repo(root: Path) -> None:
    (root / "main.py").write_text(
        "def add(a: int, b: int) -> int:\n" '    """Add two numbers."""\n' "    return a + b\n"
    )
    (root / "README.md").write_text("# Title\n\nSome descriptive paragraph text.\n")
    (root / "ignored.py").write_text("SECRET = 1\n")
    (root / ".gitignore").write_text("ignored.py\n")
    node_modules = root / "node_modules"
    node_modules.mkdir()
    (node_modules / "big.js").write_text("var x = 1;\n")


def _make_repository(workspace_id: object = None) -> Repository:
    now = datetime.now(UTC)
    return Repository(
        id=uuid4(),
        workspace_id=uuid4() if workspace_id is None else workspace_id,  # type: ignore[arg-type]
        source_type=RepositorySourceType.GIT_URL,
        git_url="https://github.com/example/repo.git",
        default_branch="main",
        local_path=None,
        last_indexed_commit_sha=None,
        status=RepositoryStatus.INDEXING,
        created_at=now,
        updated_at=now,
    )


def _make_job(repository_id: object) -> IndexingJob:
    now = datetime.now(UTC)
    return IndexingJob(
        id=uuid4(),
        repository_id=repository_id,  # type: ignore[arg-type]
        celery_task_id=None,
        status=IndexingJobStatus.QUEUED,
        stage_detail=None,
        files_total=0,
        files_processed=0,
        chunks_total=0,
        error_message=None,
        retry_count=0,
        started_at=None,
        finished_at=None,
        created_at=now,
    )


def _build_use_case(
    repo_repo: FakeRepositoryRepository,
    job_repo: FakeIndexingJobRepository,
    file_repo: FakeFileRepository,
    chunk_repo: FakeChunkRepository,
    git_port: FakeGitPort,
    embedding_port: FakeEmbeddingPort,
    vector_store: FakeVectorStorePort,
    commit=None,
) -> RunIndexingPipelineUseCase:
    return RunIndexingPipelineUseCase(
        repository_repo=repo_repo,  # type: ignore[arg-type]
        indexing_job_repo=job_repo,  # type: ignore[arg-type]
        file_repo=file_repo,  # type: ignore[arg-type]
        chunk_repo=chunk_repo,  # type: ignore[arg-type]
        git_port=git_port,  # type: ignore[arg-type]
        embedding_port=embedding_port,  # type: ignore[arg-type]
        vector_store_port=vector_store,  # type: ignore[arg-type]
        max_chunk_tokens=_MAX_CHUNK_TOKENS,
        min_chunk_tokens=_MIN_CHUNK_TOKENS,
        merge_target_tokens=_MERGE_TARGET_TOKENS,
        max_file_size_bytes=_MAX_FILE_SIZE_BYTES,
        excluded_dir_names=_EXCLUDED_DIR_NAMES,
        embedding_version="fake-embed-v1",
        commit=commit,
    )


async def test_execute_indexes_repository_end_to_end(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    repo_repo = FakeRepositoryRepository()
    job_repo = FakeIndexingJobRepository()
    file_repo = FakeFileRepository()
    chunk_repo = FakeChunkRepository()
    git_port = FakeGitPort(
        ClonedRepo(local_path=tmp_path, commit_sha="abc123", default_branch="main", size_bytes=1)
    )
    embedding_port = FakeEmbeddingPort()
    vector_store = FakeVectorStorePort()

    repository = await repo_repo.add(_make_repository())
    job = await job_repo.add(_make_job(repository.id))

    use_case = _build_use_case(
        repo_repo, job_repo, file_repo, chunk_repo, git_port, embedding_port, vector_store
    )
    await use_case.execute(job.id)

    completed_job = job_repo.jobs[job.id]
    assert completed_job.status == IndexingJobStatus.COMPLETED
    # main.py + README.md + .gitignore itself (walked like any other file
    # — it just has no parser and isn't markdown, so it yields 0 chunks).
    # ignored.py is excluded via .gitignore, node_modules via directory-
    # name pruning.
    assert completed_job.files_total == 3
    assert completed_job.files_processed == 3
    assert completed_job.chunks_total > 0

    updated_repository = repo_repo.repositories[repository.id]
    assert updated_repository.status == RepositoryStatus.READY
    assert updated_repository.last_indexed_commit_sha == "abc123"

    persisted_paths = {f.path for f in file_repo.files.values()}
    assert persisted_paths == {"main.py", "README.md"}

    assert len(chunk_repo.chunks) == completed_job.chunks_total
    assert all(c.embedding_model == "fake-embed-v1" for c in chunk_repo.chunks.values())

    assert vector_store.upsert_calls == 2  # one upsert call per processed file
    assert len(vector_store.upserted) == completed_job.chunks_total
    assert all(item.workspace_id == repository.workspace_id for item in vector_store.upserted)
    assert all(item.embedding_version == "fake-embed-v1" for item in vector_store.upserted)


async def test_execute_skips_unchanged_files_on_reindex(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    repo_repo = FakeRepositoryRepository()
    job_repo = FakeIndexingJobRepository()
    file_repo = FakeFileRepository()
    chunk_repo = FakeChunkRepository()
    git_port = FakeGitPort(
        ClonedRepo(local_path=tmp_path, commit_sha="abc123", default_branch="main", size_bytes=1)
    )
    embedding_port = FakeEmbeddingPort()
    vector_store = FakeVectorStorePort()

    repository = await repo_repo.add(_make_repository())
    first_job = await job_repo.add(_make_job(repository.id))
    use_case = _build_use_case(
        repo_repo, job_repo, file_repo, chunk_repo, git_port, embedding_port, vector_store
    )
    await use_case.execute(first_job.id)
    chunks_after_first_run = len(chunk_repo.chunks)
    assert chunks_after_first_run > 0

    second_job = await job_repo.add(_make_job(repository.id))
    await use_case.execute(second_job.id)

    completed_second_job = job_repo.jobs[second_job.id]
    # Nothing changed on disk since the first run, so content_hash matches
    # for every file and the whole file is skipped — no new chunks, no
    # deactivation of the still-current ones.
    assert completed_second_job.chunks_total == 0
    assert len(chunk_repo.chunks) == chunks_after_first_run
    assert chunk_repo.deactivated_files == []


async def test_execute_isolates_a_single_file_failure(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)
    (tmp_path / "broken.py").write_text(
        "def trigger_failure() -> str:\n    return 'TRIGGER_FAILURE'\n"
    )

    repo_repo = FakeRepositoryRepository()
    job_repo = FakeIndexingJobRepository()
    file_repo = FakeFileRepository()
    chunk_repo = FakeChunkRepository()
    git_port = FakeGitPort(
        ClonedRepo(local_path=tmp_path, commit_sha="abc123", default_branch="main", size_bytes=1)
    )
    embedding_port = FakeEmbeddingPort(fail_on_marker="TRIGGER_FAILURE")
    vector_store = FakeVectorStorePort()

    repository = await repo_repo.add(_make_repository())
    job = await job_repo.add(_make_job(repository.id))
    use_case = _build_use_case(
        repo_repo, job_repo, file_repo, chunk_repo, git_port, embedding_port, vector_store
    )
    await use_case.execute(job.id)

    completed_job = job_repo.jobs[job.id]
    # The whole job still completes despite broken.py's embedding call
    # raising — per-file isolation, not all-or-nothing. main.py +
    # README.md + .gitignore + broken.py.
    assert completed_job.status == IndexingJobStatus.COMPLETED
    assert completed_job.files_total == 4
    assert completed_job.files_processed == 4
    persisted_paths = {f.path for f in file_repo.files.values()}
    assert "broken.py" not in persisted_paths
    assert {"main.py", "README.md"}.issubset(persisted_paths)


async def test_execute_marks_job_and_repository_failed_on_clone_error() -> None:
    class _ExplodingGitPort:
        async def clone(self, url: str, dest_dir: Path, *, shallow: bool = True) -> ClonedRepo:
            raise RuntimeError("network unreachable")

        async def get_blame(
            self, repo_path: Path, file_path: str, start_line: int, end_line: int
        ) -> list:  # type: ignore[type-arg]
            return []

    repo_repo = FakeRepositoryRepository()
    job_repo = FakeIndexingJobRepository()
    file_repo = FakeFileRepository()
    chunk_repo = FakeChunkRepository()
    embedding_port = FakeEmbeddingPort()
    vector_store = FakeVectorStorePort()

    repository = await repo_repo.add(_make_repository())
    job = await job_repo.add(_make_job(repository.id))
    use_case = _build_use_case(
        repo_repo,
        job_repo,
        file_repo,
        chunk_repo,
        _ExplodingGitPort(),
        embedding_port,
        vector_store,
    )

    try:
        await use_case.execute(job.id)
        raised = False
    except RuntimeError:
        raised = True
    assert raised

    failed_job = job_repo.jobs[job.id]
    assert failed_job.status == IndexingJobStatus.FAILED
    assert failed_job.error_message == "network unreachable"
    assert repo_repo.repositories[repository.id].status == RepositoryStatus.FAILED


async def test_execute_commits_after_every_file_not_once_at_the_end(tmp_path: Path) -> None:
    """A real Celery worker wraps the whole job in one session — without
    a per-file commit, a crash mid-job rolls back every file processed
    so far, even ones whose vectors already landed in Qdrant (which
    isn't part of this transaction and won't roll back with it). This
    pins the fix: commit() must fire after each file, not only once at
    the very end."""
    _write_fixture_repo(tmp_path)

    repo_repo = FakeRepositoryRepository()
    job_repo = FakeIndexingJobRepository()
    file_repo = FakeFileRepository()
    chunk_repo = FakeChunkRepository()
    git_port = FakeGitPort(
        ClonedRepo(local_path=tmp_path, commit_sha="abc123", default_branch="main", size_bytes=1)
    )
    embedding_port = FakeEmbeddingPort()
    vector_store = FakeVectorStorePort()
    commit_calls = 0

    async def _commit() -> None:
        nonlocal commit_calls
        commit_calls += 1

    repository = await repo_repo.add(_make_repository())
    job = await job_repo.add(_make_job(repository.id))
    use_case = _build_use_case(
        repo_repo,
        job_repo,
        file_repo,
        chunk_repo,
        git_port,
        embedding_port,
        vector_store,
        commit=_commit,
    )
    await use_case.execute(job.id)

    # One commit per walked file (main.py, README.md, .gitignore) plus
    # one for the WALKING->PARSING transition and one for COMPLETED —
    # the exact count matters less than that it's clearly more than 1,
    # proving progress is flushed incrementally rather than in a single
    # end-of-job commit.
    assert commit_calls >= 3 + 2


async def test_execute_commits_the_failure_before_reraising(tmp_path: Path) -> None:
    """If a caller's own transaction rolls back on the re-raised
    exception (the real Celery task's db_session_context does exactly
    this), the FAILED status must already be durably committed by then
    — otherwise the rollback silently discards the only record that the
    job failed."""

    class _ExplodingGitPort:
        async def clone(self, url: str, dest_dir: Path, *, shallow: bool = True) -> ClonedRepo:
            raise RuntimeError("network unreachable")

        async def get_blame(
            self, repo_path: Path, file_path: str, start_line: int, end_line: int
        ) -> list:  # type: ignore[type-arg]
            return []

    repo_repo = FakeRepositoryRepository()
    job_repo = FakeIndexingJobRepository()
    file_repo = FakeFileRepository()
    chunk_repo = FakeChunkRepository()
    embedding_port = FakeEmbeddingPort()
    vector_store = FakeVectorStorePort()
    commit_calls = 0

    async def _commit() -> None:
        nonlocal commit_calls
        commit_calls += 1

    repository = await repo_repo.add(_make_repository())
    job = await job_repo.add(_make_job(repository.id))
    use_case = _build_use_case(
        repo_repo,
        job_repo,
        file_repo,
        chunk_repo,
        _ExplodingGitPort(),
        embedding_port,
        vector_store,
        commit=_commit,
    )

    with pytest.raises(RuntimeError):
        await use_case.execute(job.id)

    assert commit_calls >= 1
    assert job_repo.jobs[job.id].status == IndexingJobStatus.FAILED
