from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.correlation_id import CorrelationIdMiddleware
from app.api.routers import auth, health
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(title="CodeAtlas", version="0.1.0")

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

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
