from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    """Wraps list/paginated responses only — a single-resource endpoint
    (e.g. GET .../workspaces/{id}) returns its model directly, per
    DESIGN.md §16."""

    data: T
    meta: dict[str, object] = Field(default_factory=dict)


class ProblemDetail(BaseModel):
    """RFC 7807 error body, produced exclusively by the global exception
    handlers in app/api/middleware/error_handling.py — routers should
    never construct this directly."""

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    correlation_id: str | None = None
