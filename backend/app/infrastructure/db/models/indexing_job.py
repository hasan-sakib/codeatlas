from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.indexing_job import IndexingJobStatus
from app.infrastructure.db.base import Base


class IndexingJobModel(Base):
    __tablename__ = "indexing_jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[IndexingJobStatus] = mapped_column(
        SAEnum(IndexingJobStatus, native_enum=False, validate_strings=True),
        nullable=False,
        default=IndexingJobStatus.QUEUED,
        index=True,
    )
    stage_detail: Mapped[str | None] = mapped_column(String, nullable=True)
    files_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
