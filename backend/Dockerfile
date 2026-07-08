# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /build
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Dependencies synced from the committed lockfile (--frozen: fail rather
# than silently re-resolve if pyproject.toml and uv.lock ever drift) in
# their own layer, before app code is copied in — editing app/ doesn't
# invalidate this layer's cache. --no-dev excludes pytest/mypy/ruff/etc,
# which have no business in a runtime image.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

# GitPython (used by the repository-cloning adapter) shells out to a real
# `git` binary and fails at import time — not just at clone time — if
# it's missing, so this isn't optional even though nothing at container
# startup obviously "needs" git.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --create-home app

# Without a persistent, explicitly-located cache dir, every container
# recreation re-downloads BGE-M3/the reranker's multi-GB weights from
# HuggingFace from scratch — verified directly: a fresh container took
# several minutes on first embedding call. infra/docker/docker-compose.yml
# mounts a named volume here.
RUN mkdir -p /data/hf-cache && chown app:app /data/hf-cache
ENV HF_HOME=/data/hf-cache

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
