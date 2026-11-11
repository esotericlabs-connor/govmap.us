import asyncio
import logging
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.db import async_session_factory
from app.models.pipeline_status import PipelineStatusRow

logger = logging.getLogger(__name__)
router = APIRouter()
READINESS_TIMEOUT_SECONDS = 3


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    commit_sha: str | None


def _response(ready: bool) -> JSONResponse:
    body = HealthResponse(
        status="ok" if ready else "unavailable",
        commit_sha=None if settings.app_commit_sha == "unknown" else settings.app_commit_sha,
    )
    return JSONResponse(
        status_code=200 if ready else 503,
        content=body.model_dump(),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> JSONResponse:
    return _response(True)


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
)
async def ready() -> JSONResponse:
    try:
        async with asyncio.timeout(READINESS_TIMEOUT_SECONDS):
            async with async_session_factory() as session:
                # Reading an empty table is healthy; its absence is not.
                await session.execute(select(PipelineStatusRow.source).limit(1))
    except (SQLAlchemyError, TimeoutError, OSError) as exc:
        # Driver exception messages may contain credentials or host addresses.
        logger.warning("database readiness check failed (%s)", type(exc).__name__)
        return _response(False)
    return _response(True)
