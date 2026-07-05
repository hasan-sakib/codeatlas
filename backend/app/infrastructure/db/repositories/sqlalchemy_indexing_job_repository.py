from uuid import UUID

from sqlalchemy import select

from app.domain.entities.indexing_job import IndexingJob
from app.domain.ports.indexing_job_repository import IndexingJobRepository
from app.infrastructure.db.models.indexing_job import IndexingJobModel
from app.infrastructure.db.repositories.base_repository import SqlAlchemyRepository


def _to_entity(model: IndexingJobModel) -> IndexingJob:
    return IndexingJob(
        id=model.id,
        repository_id=model.repository_id,
        celery_task_id=model.celery_task_id,
        status=model.status,
        stage_detail=model.stage_detail,
        files_total=model.files_total,
        files_processed=model.files_processed,
        chunks_total=model.chunks_total,
        error_message=model.error_message,
        retry_count=model.retry_count,
        started_at=model.started_at,
        finished_at=model.finished_at,
        created_at=model.created_at,
    )


class SqlAlchemyIndexingJobRepository(SqlAlchemyRepository, IndexingJobRepository):
    async def add(self, job: IndexingJob) -> IndexingJob:
        model = IndexingJobModel(
            id=job.id,
            repository_id=job.repository_id,
            celery_task_id=job.celery_task_id,
            status=job.status,
            stage_detail=job.stage_detail,
            files_total=job.files_total,
            files_processed=job.files_processed,
            chunks_total=job.chunks_total,
            error_message=job.error_message,
            retry_count=job.retry_count,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)

    async def get_by_id(self, job_id: UUID) -> IndexingJob | None:
        model = await self.session.get(IndexingJobModel, job_id)
        return _to_entity(model) if model else None

    async def list_by_repository(self, repository_id: UUID) -> list[IndexingJob]:
        result = await self.session.execute(
            select(IndexingJobModel)
            .where(IndexingJobModel.repository_id == repository_id)
            .order_by(IndexingJobModel.created_at.desc())
        )
        return [_to_entity(m) for m in result.scalars().all()]

    async def update(self, job: IndexingJob) -> IndexingJob:
        model = await self.session.get(IndexingJobModel, job.id)
        if model is None:
            raise ValueError(f"IndexingJob {job.id} not found")
        model.celery_task_id = job.celery_task_id
        model.status = job.status
        model.stage_detail = job.stage_detail
        model.files_total = job.files_total
        model.files_processed = job.files_processed
        model.chunks_total = job.chunks_total
        model.error_message = job.error_message
        model.retry_count = job.retry_count
        model.started_at = job.started_at
        model.finished_at = job.finished_at
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)
