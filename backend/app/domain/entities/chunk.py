from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class SymbolKind(str, Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    VARIABLE = "variable"
    DOCSTRING = "docstring"
    MARKDOWN_SECTION = "markdown_section"
    OTHER = "other"


class ChunkType(str, Enum):
    CODE = "code"
    PROSE = "prose"


@dataclass(frozen=True)
class Chunk:
    # id doubles as the Qdrant point id (see Module 10) — never regenerate
    # this on reindex without also updating the corresponding vector point.
    id: UUID
    file_id: UUID
    repository_id: UUID
    symbol_name: str | None
    symbol_kind: SymbolKind
    start_line: int
    end_line: int
    content: str
    content_tokens: int
    chunk_type: ChunkType
    imports: list[str] = field(default_factory=list)
    git_blame: dict[str, Any] | None = None
    embedding_model: str | None = None
    embedding_version: int | None = None
    is_active: bool = True
    created_at: datetime | None = None
