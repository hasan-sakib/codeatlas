from typing import Literal

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter()
logger = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    logger.info("health_check.requested")
    return HealthResponse(status="ok", version=__version__)
