from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import health

# Placeholder origin list — replaced by Module 2's Settings.cors_origins once
# the configuration system lands; kept hardcoded here so Module 1 has no
# dependency on modules that don't exist yet.
_DEV_CORS_ORIGINS = ["http://localhost:3000"]


def create_app() -> FastAPI:
    app = FastAPI(title="CodeAtlas", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_DEV_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
