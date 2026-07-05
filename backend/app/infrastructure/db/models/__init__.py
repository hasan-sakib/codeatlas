"""Import every model module so Base.metadata is fully populated for
Alembic autogenerate and for `Base.metadata.create_all()` in tests.
"""

from app.infrastructure.db.models import (  # noqa: F401
    chunk,
    conversation,
    file,
    indexing_job,
    message,
    refresh_token,
    repository,
    user,
    workspace,
)

__all__ = [
    "chunk",
    "conversation",
    "file",
    "indexing_job",
    "message",
    "refresh_token",
    "repository",
    "user",
    "workspace",
]
