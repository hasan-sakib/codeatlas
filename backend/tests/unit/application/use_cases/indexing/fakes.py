from dataclasses import replace
from uuid import UUID

from app.domain.entities.indexing_job import IndexingJob
from app.domain.entities.repository import Repository, RepositoryStatus


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
