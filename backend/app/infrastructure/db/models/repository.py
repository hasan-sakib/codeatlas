from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.repository import RepositorySourceType, RepositoryStatus
from app.infrastructure.db.base import Base


class RepositoryModel(Base):
    __tablename__ = "repositories"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # native_enum=False renders as VARCHAR + CHECK constraint instead of a
    # native Postgres ENUM type — avoids ALTER TYPE ceremony in future
    # Alembic migrations when a new status/source value is added.
    source_type: Mapped[RepositorySourceType] = mapped_column(
        SAEnum(RepositorySourceType, native_enum=False, validate_strings=True), nullable=False
    )
    git_url: Mapped[str | None] = mapped_column(String, nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String, nullable=True)
    local_path: Mapped[str | None] = mapped_column(String, nullable=True)
    last_indexed_commit_sha: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[RepositoryStatus] = mapped_column(
        SAEnum(RepositoryStatus, native_enum=False, validate_strings=True),
        nullable=False,
        default=RepositoryStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
