from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class SSEEventName(str, Enum):
    TOKEN = "token"
    CITATION = "citation"
    PROGRESS = "progress"
    DONE = "done"
    ERROR = "error"


class TokenEvent(BaseModel):
    text: str


class CitationEvent(BaseModel):
    chunk_id: UUID
    file_path: str
    start_line: int
    end_line: int
    score: float


class ProgressEvent(BaseModel):
    stage: str
    percent: float | None = None
    message: str | None = None


class DoneEvent(BaseModel):
    message_id: UUID | None = None


class ErrorEvent(BaseModel):
    type: str
    title: str
    detail: str | None = None
