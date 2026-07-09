from typing import Literal

import structlog
from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app import __version__
from app.core.observability.health_checks import DependencyStatus, check_all_dependencies

router = APIRouter()
logger = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    dependencies: list[DependencyStatus]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    logger.info("health_check.requested")
    return HealthResponse(status="ok", version=__version__)


@router.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Process-is-up only — deliberately never calls check_all_dependencies.
    A dependency outage must not make the orchestrator kill and restart a
    perfectly healthy process; that's exactly what /health/ready is for."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(response: Response) -> ReadinessResponse:
    dependencies = await check_all_dependencies()
    all_healthy = all(dep.healthy for dep in dependencies)
    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning(
            "readiness_check.unhealthy",
            unhealthy=[dep.name for dep in dependencies if not dep.healthy],
        )
    return ReadinessResponse(
        status="ok" if all_healthy else "unavailable", dependencies=dependencies
    )
