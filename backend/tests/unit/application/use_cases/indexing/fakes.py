from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from app.domain.entities.chunk import Chunk
from app.domain.entities.file import File
from app.domain.entities.indexing_job import IndexingJob
from app.domain.entities.repository import Repository, RepositoryStatus
from app.domain.value_objects.chunk_upsert_item import ChunkUpsertItem
from app.domain.value_objects.clone_result import BlameEntry, ClonedRepo
from app.domain.value_objects.embedding_result import EmbeddingResult


class FakeRepositoryRepository:
    def __init__(self) -> None:
        self.repositories: dict[UUID, Repository] = {}

    async def add(self, repository: Repository) -> Repository:
        self.repositories[repository.id] = repository
        return repository

    async def get_by_id(self, repository_id: UUID) -> Repository | None:
        return self.repositories.get(repository_id)

    async def list_by_workspace(self, workspace_id: UUID) -> list[Repository]:
        return [r for r in self.repositories.values() if r.workspace_id == workspace_id]

    async def update_status(
        self,
        repository_id: UUID,
        status: RepositoryStatus,
        *,
        last_indexed_commit_sha: str | None = None,
    ) -> None:
        repository = self.repositories.get(repository_id)
        if repository is None:
            return
        updated = replace(repository, status=status)
        if last_indexed_commit_sha is not None:
            updated = replace(updated, last_indexed_commit_sha=last_indexed_commit_sha)
        self.repositories[repository_id] = updated

    async def delete(self, repository_id: UUID) -> None:
        self.repositories.pop(repository_id, None)


class FakeIndexingJobRepository:
    def __init__(self) -> None:
        self.jobs: dict[UUID, IndexingJob] = {}
        self.add_call_count = 0

    async def add(self, job: IndexingJob) -> IndexingJob:
        self.add_call_count += 1
        self.jobs[job.id] = job
        return job

    async def get_by_id(self, job_id: UUID) -> IndexingJob | None:
        return self.jobs.get(job_id)

    async def list_by_repository(self, repository_id: UUID) -> list[IndexingJob]:
        return [j for j in self.jobs.values() if j.repository_id == repository_id]

    async def update(self, job: IndexingJob) -> IndexingJob:
        self.jobs[job.id] = job
        return job


class FakeIndexingTaskDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[UUID] = []

    async def dispatch(self, job_id: UUID) -> str:
        self.dispatched.append(job_id)
        return f"fake-task-{job_id}"


class FakeFileRepository:
    def __init__(self) -> None:
        self.files: dict[UUID, File] = {}

    async def add(self, file: File) -> File:
        self.files[file.id] = file
        return file

    async def get_by_id(self, file_id: UUID) -> File | None:
        return self.files.get(file_id)

    async def get_by_ids(self, file_ids: Sequence[UUID]) -> list[File]:
        return [self.files[i] for i in file_ids if i in self.files]

    async def get_by_repository_and_path(self, repository_id: UUID, path: str) -> File | None:
        return next(
            (f for f in self.files.values() if f.repository_id == repository_id and f.path == path),
            None,
        )

    async def list_by_repository(self, repository_id: UUID) -> list[File]:
        return [f for f in self.files.values() if f.repository_id == repository_id]

    async def upsert(self, file: File) -> File:
        self.files[file.id] = file
        return file


class FakeChunkRepository:
    def __init__(self) -> None:
        self.chunks: dict[UUID, Chunk] = {}
        self.deactivated_files: list[UUID] = []

    async def add_many(self, chunks: Sequence[Chunk]) -> None:
        for chunk in chunks:
            self.chunks[chunk.id] = chunk

    async def get_by_id(self, chunk_id: UUID) -> Chunk | None:
        return self.chunks.get(chunk_id)

    async def get_by_ids(self, chunk_ids: Sequence[UUID]) -> list[Chunk]:
        return [self.chunks[i] for i in chunk_ids if i in self.chunks]

    async def list_by_file(self, file_id: UUID) -> list[Chunk]:
        return [c for c in self.chunks.values() if c.file_id == file_id]

    async def deactivate_by_file(self, file_id: UUID) -> None:
        self.deactivated_files.append(file_id)
        for chunk_id, chunk in list(self.chunks.items()):
            if chunk.file_id == file_id:
                self.chunks[chunk_id] = replace(chunk, is_active=False)

    async def delete_by_file(self, file_id: UUID) -> None:
        self.chunks = {i: c for i, c in self.chunks.items() if c.file_id != file_id}

    async def delete_by_repository(self, repository_id: UUID) -> None:
        self.chunks = {i: c for i, c in self.chunks.items() if c.repository_id != repository_id}


class FakeGitPort:
    """Fakes only the network boundary — `clone()` returns a caller-supplied
    local directory instead of actually cloning, so tests exercise the real
    walker/parser/chunker against real files on disk without network access.
    """

    def __init__(self, cloned_repo: ClonedRepo, blame: list[BlameEntry] | None = None) -> None:
        self._cloned_repo = cloned_repo
        self._blame = blame if blame is not None else []
        self.clone_calls: list[str] = []

    async def clone(self, url: str, dest_dir: Path, *, shallow: bool = True) -> ClonedRepo:
        self.clone_calls.append(url)
        return self._cloned_repo

    async def get_blame(
        self, repo_path: Path, file_path: str, start_line: int, end_line: int
    ) -> list[BlameEntry]:
        return self._blame


class FakeEmbeddingPort:
    """Deterministic, order-preserving fake. `fail_on_marker`, if set,
    raises when any input text contains that substring — used to test
    per-file error isolation without needing a real broken source file."""

    def __init__(self, fail_on_marker: str | None = None) -> None:
        self._fail_on_marker = fail_on_marker
        self.embedded_texts: list[str] = []

    async def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingResult]:
        if self._fail_on_marker is not None and any(self._fail_on_marker in t for t in texts):
            raise RuntimeError("simulated embedding failure")
        self.embedded_texts.extend(texts)
        return [
            EmbeddingResult(dense=[0.1, 0.2, 0.3, 0.4], sparse={1: 0.5}, model_id="fake-embed-v1")
            for _ in texts
        ]

    async def embed_query(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            dense=[0.1, 0.2, 0.3, 0.4], sparse={1: 0.5}, model_id="fake-embed-v1"
        )

    async def warm_up(self) -> None:
        return None


class FakeVectorStorePort:
    def __init__(self) -> None:
        self.upserted: list[ChunkUpsertItem] = []
        self.upsert_calls: int = 0

    async def upsert(self, items: Sequence[ChunkUpsertItem], *, workspace_id: UUID) -> None:
        self.upsert_calls += 1
        for item in items:
            assert item.workspace_id == workspace_id
        self.upserted.extend(items)
