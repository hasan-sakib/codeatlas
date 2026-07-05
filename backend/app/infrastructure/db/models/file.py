from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class FileModel(Base):
    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("repository_id", "path", name="uq_files_repository_path"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    last_commit_sha: Mapped[str | None] = mapped_column(String, nullable=True)
    last_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
