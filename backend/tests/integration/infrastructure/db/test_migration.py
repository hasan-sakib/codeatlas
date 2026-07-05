import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[4]

EXPECTED_TABLES = {
    "users",
    "workspaces",
    "repositories",
    "indexing_jobs",
    "files",
    "chunks",
    "conversations",
    "messages",
    "refresh_tokens",
    "alembic_version",
}


async def test_alembic_upgrade_head_creates_all_tables_on_a_fresh_database() -> None:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        url = container.get_connection_url()
        env = {
            **os.environ,
            "DATABASE__URL": url,
            "QDRANT__URL": "http://localhost:6333",
            "REDIS__URL": "redis://localhost:6379/0",
            "OLLAMA__BASE_URL": "http://localhost:11434",
            "SECURITY__JWT_SECRET_KEY": "test-secret",
        }

        result = subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                table_names = set(
                    await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
                )
        finally:
            await engine.dispose()

        assert EXPECTED_TABLES.issubset(table_names)
