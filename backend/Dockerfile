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

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY app ./app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
