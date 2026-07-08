from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str
    language: str | None = None
    path_prefix: str | None = None
    symbol_kind: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class SearchResultItem(BaseModel):
    chunk_id: UUID
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str | None
    score: float
    source: str
    text: str | None
