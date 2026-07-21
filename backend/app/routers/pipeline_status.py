"""Internal pipeline health endpoint.

NOTE: unauthenticated. That's acceptable for local-only development but not
for anything reachable through the cloudflared tunnel — see AGENTS.md ->
Security & review gate. Add access control before this is deployed anywhere
but localhost.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/internal", tags=["internal"])

# backend/app/routers/pipeline_status.py -> parents[2] == backend/
STATUS_PATH = Path(__file__).resolve().parents[2] / "data" / "pipeline_status.json"


@router.get("/pipeline-status")
async def pipeline_status() -> dict:
    if not STATUS_PATH.exists():
        raise HTTPException(status_code=404, detail="no pipeline runs recorded yet")
    return json.loads(STATUS_PATH.read_text())
