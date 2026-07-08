"""messages.created_at uses clock_timestamp() instead of now()

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-08 12:00:00.000000

now() returns the *transaction* start time in Postgres, not per-statement
wall-clock time. Multiple messages appended within one session/request
(the normal case for a conversation) all received an identical
created_at, making MessageRepository.list_recent's `ORDER BY created_at
DESC` non-deterministic for chronological ordering — caught by a real
Postgres integration test in Module 15, not by code review.
clock_timestamp() returns true per-statement time instead.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "messages",
        "created_at",
        server_default=sa.text("clock_timestamp()"),
    )


def downgrade() -> None:
    op.alter_column(
        "messages",
        "created_at",
        server_default=sa.text("now()"),
    )
