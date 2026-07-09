from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.correlation_id import CorrelationIdMiddleware
from app.api.middleware.error_handling import register_exception_handlers
from app.api.routers import auth, conversations, docs, health, repositories, search, workspaces
from app.core.config import get_settings
from app.core.di import provide_embedding_port
from app.core.logging import configure_logging
from app.core.observability.instrumentation import setup_prometheus_instrumentator

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Loading BGE-M3 takes anywhere from seconds (warm disk cache) to
    # several minutes (cold HuggingFace download, or just slow disk I/O —
    # verified directly in a container) — paying that cost here, before
    # accepting any traffic, means the container's own healthcheck is
    # what makes this visible (`depends_on: condition: service_healthy`
    # blocks correctly) instead of the first real user silently waiting
    # minutes for what looks like a hung request.
    #
    # Skipped when ENVIRONMENT=test: tests/integration/api/conftest.py's
    # `api_client` fixture uses `with TestClient(create_app()) as client`,
    # which *does* run this lifespan (unlike a plain `TestClient(...)`
    # without `with` — Starlette only wires up lifespan through the
    # context-manager protocol) — without this gate, every test using
    # that fixture would load the real multi-GB model.
    settings = get_settings()
    if settings.environment == "test":
        logger.info("startup.embedding_warmup_skipped_for_tests")
    else:
        logger.info("startup.warming_up_embedding_model")
        await provide_embedding_port().warm_up()
        logger.info("startup.embedding_model_ready")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(title="CodeAtlas", version="0.1.0", lifespan=lifespan)
    register_exception_handlers(app)
    setup_prometheus_instrumentator(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Added last so it becomes the outermost middleware layer (Starlette
    # runs the most-recently-added middleware first on the way in) —
    # correlation id must be bound before any other middleware that logs.
    app.add_middleware(CorrelationIdMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(workspaces.router)
    app.include_router(repositories.router)
    app.include_router(search.router)
    app.include_router(conversations.router)
    app.include_router(docs.router)

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
