"""Internal pipeline health endpoint, backed by the pipeline_status table.

Access-controlled with HTTP Basic Auth. Credentials come from INTERNAL_USER /
INTERNAL_PASSWORD (see app/config.py); if either is unset the endpoint denies
every request, so it's locked by default rather than accidentally public — the
tunnel exposes this backend at api.govmap.us, so an open /internal/* would be
reachable from the internet.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.pipeline_status import PipelineStatusRow

router = APIRouter(prefix="/internal", tags=["internal"])
security = HTTPBasic()


def require_internal_auth(
    credentials: HTTPBasicCredentials = Depends(security),
) -> None:
    configured = bool(settings.internal_user and settings.internal_password)
    user_ok = configured and secrets.compare_digest(
        credentials.username, settings.internal_user
    )
    password_ok = configured and secrets.compare_digest(
        credentials.password, settings.internal_password
    )
    if not (user_ok and password_ok):
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
