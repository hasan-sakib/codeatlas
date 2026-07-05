from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.chunk import ChunkType, SymbolKind
from app.infrastructure.db.base import Base


class ChunkModel(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index(
            "ix_chunks_repository_active_version",
            "repository_id",
            "is_active",
            "embedding_version",
        ),
    )

    # == Qdrant point id (see Module 10) — generated in Python (uuid4), not
    # server-side, since it must be known before the Qdrant upsert call.
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    symbol_name: Mapped[str | None] = mapped_column(String, nullable=True)
    symbol_kind: Mapped[SymbolKind] = mapped_column(
        SAEnum(SymbolKind, native_enum=False, validate_strings=True), nullable=False
    )
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_type: Mapped[ChunkType] = mapped_column(
        SAEnum(ChunkType, native_enum=False, validate_strings=True), nullable=False
    )
    imports: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    git_blame: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
