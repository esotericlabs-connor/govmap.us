"""Internal pipeline health endpoints, backed by the pipeline_status and
source_runs tables.

Access-controlled with HTTP Basic Auth. Credentials come from INTERNAL_USER /
INTERNAL_PASSWORD (see app/config.py); if either is unset the endpoint denies
every request, so it's locked by default rather than accidentally public — the
tunnel exposes this backend at api.govmap.us, so an open /internal/* would be
reachable from the internet.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.pipeline_status import PipelineStatusRow
from app.models.source_run import RUN_OUTCOMES, SourceRun
from app.sources import SOURCES

router = APIRouter(prefix="/internal", tags=["internal"])
security = HTTPBasic()


def _matches(supplied: str, expected: str) -> bool:
    # compare_digest raises TypeError on non-ASCII str, which would turn a bad
    # login into a 500; comparing UTF-8 bytes keeps it constant-time and a 401.
    return secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


def require_internal_auth(
    credentials: HTTPBasicCredentials = Depends(security),
) -> None:
    configured = bool(settings.internal_user and settings.internal_password)
    # Evaluate both comparisons unconditionally so timing doesn't reveal which
    # half of the credential pair was wrong.
    user_ok = _matches(credentials.username, settings.internal_user)
    password_ok = _matches(credentials.password, settings.internal_password)
    if not (configured and user_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/pipeline-status", dependencies=[Depends(require_internal_auth)])
async def pipeline_status(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await db.execute(
        select(PipelineStatusRow).order_by(PipelineStatusRow.source)
    )
    return [
        {
            "source": row.source,
            "last_run": row.last_run.isoformat() if row.last_run else None,
            "last_success": row.last_success.isoformat() if row.last_success else None,
            "record_count": row.record_count,
            "status": row.status,
            "detail": row.detail,
        }
        for row in result.scalars().all()
    ]


class SourceRunQuery(BaseModel):
    # Forbid unknown parameters: a misspelled filter must fail, not silently
    # return unfiltered history.
    model_config = ConfigDict(extra="forbid")

    source: str | None = Field(default=None, max_length=50)
    outcome: str | None = Field(default=None, max_length=20)
    before_id: int | None = Field(default=None, ge=1)
    limit: int = Field(default=100, ge=1, le=500)

    @field_validator("source")
    @classmethod
    def _registered_source(cls, value: str | None) -> str | None:
        if value is not None and value not in SOURCES:
            raise ValueError("not a registered source")
        return value

    @field_validator("outcome")
    @classmethod
    def _known_outcome(cls, value: str | None) -> str | None:
        if value is not None and value not in RUN_OUTCOMES:
            raise ValueError(f"must be one of: {', '.join(RUN_OUTCOMES)}")
        return value


@router.get("/source-runs", dependencies=[Depends(require_internal_auth)])
async def source_runs(
    query: Annotated[SourceRunQuery, Query()],
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Refresh-run history, newest first. To page back, pass the smallest id
    of the previous page as before_id. Details were redacted when written."""
    stmt = select(SourceRun).order_by(SourceRun.id.desc()).limit(query.limit)
    if query.source is not None:
        stmt = stmt.where(SourceRun.source == query.source)
    if query.outcome is not None:
        stmt = stmt.where(SourceRun.outcome == query.outcome)
    if query.before_id is not None:
        stmt = stmt.where(SourceRun.id < query.before_id)
    result = await db.execute(stmt)
    return [
        {
            "id": row.id,
            "source": row.source,
            "trigger": row.trigger,
            "code_version": row.code_version,
            "started_at": row.started_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "outcome": row.outcome,
            "record_count": row.record_count,
            "items_total": row.items_total,
            "items_succeeded": row.items_succeeded,
            "items_failed": row.items_failed,
            "inputs": row.inputs,
            "detail": row.detail,
        }
        for row in result.scalars().all()
    ]
