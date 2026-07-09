from functools import partial
from uuid import UUID

import structlog

from app.application.use_cases.indexing.run_indexing_pipeline import RunIndexingPipelineUseCase
from app.core.config import get_settings
from app.infrastructure.db.session import db_session_context
from app.workers.celery_app import celery_app, ensure_configured, run_in_worker_loop

logger = structlog.get_logger(__name__)


@celery_app.task(name="indexing.index_repository", bind=True, max_retries=0)  # type: ignore[untyped-decorator]
def index_repository_task(self: object, job_id: str) -> None:
    """Celery entry point for `RunIndexingPipelineUseCase`. Celery task
    bodies are sync, so this is the one place in the pipeline that
    bridges into the async use case — via `run_in_worker_loop`, not a
    fresh `asyncio.run()` per call, so the cached DB engine/Redis/Qdrant
    clients stay bound to one valid, never-closed loop across every task
    this worker process ever runs (see celery_app.py's docstring).
    """
    ensure_configured()
    run_in_worker_loop(partial(_run, UUID(job_id)))


async def _run(job_id: UUID) -> None:
    # Session-per-task (see db_session_context's docstring): a Celery
    # worker process is long-lived across many discrete task executions,
    # so each run gets its own session rather than sharing one across
    # tasks the way a single HTTP request would.
    async with db_session_context() as session:
        from app.core.di import (
            provide_chunk_repository,
            provide_embedding_port,
            provide_file_repository,
            provide_git_port,
            provide_indexing_job_repository,
            provide_repository_repository,
            provide_vector_store,
        )

        settings = get_settings()
        use_case = RunIndexingPipelineUseCase(
            repository_repo=provide_repository_repository(session),
            indexing_job_repo=provide_indexing_job_repository(session),
            file_repo=provide_file_repository(session),
            chunk_repo=provide_chunk_repository(session),
            git_port=provide_git_port(),
            embedding_port=provide_embedding_port(),
            vector_store_port=provide_vector_store(),
            max_chunk_tokens=settings.chunking.max_chunk_tokens,
            min_chunk_tokens=settings.chunking.min_chunk_tokens,
            merge_target_tokens=settings.chunking.merge_target_tokens,
            max_file_size_bytes=settings.indexing.max_file_size_bytes,
            excluded_dir_names=settings.indexing.excluded_dir_names,
            embedding_version=settings.embedding.model_id,
        )
        try:
            await use_case.execute(job_id)
        except Exception:
            logger.error("indexing_task.failed", job_id=str(job_id), exc_info=True)
            raise
