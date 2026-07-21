"""Internal pipeline health endpoint.

Access-controlled with HTTP Basic Auth. Credentials come from INTERNAL_USER /
INTERNAL_PASSWORD (see app/config.py); if either is unset the endpoint denies
every request, so it's locked by default rather than accidentally public — the
tunnel exposes this backend at api.govmap.us, so an open /internal/* would be
reachable from the internet.
"""

import json
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

router = APIRouter(prefix="/internal", tags=["internal"])
security = HTTPBasic()

# backend/app/routers/pipeline_status.py -> parents[2] == backend/
STATUS_PATH = Path(__file__).resolve().parents[2] / "data" / "pipeline_status.json"


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
async def pipeline_status() -> dict:
    if not STATUS_PATH.exists():
        raise HTTPException(status_code=404, detail="no pipeline runs recorded yet")
    return json.loads(STATUS_PATH.read_text())
