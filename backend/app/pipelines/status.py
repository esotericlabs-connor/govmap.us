"""Pipeline run status, persisted to the pipeline_status table.

Replaces the ephemeral pipeline_status.json. Every source records its outcome
here via record_run(), so /internal/pipeline-status survives restarts and the
scheduler can reason about staleness. On failure, optionally fires a webhook.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.db import async_session_factory
from app.models.pipeline_status import PipelineStatusRow

logger = logging.getLogger(__name__)


async def _maybe_alert(source: str, detail: str | None) -> None:
    url = settings.alert_webhook_url
    if not url:
        return
    try:
        await asyncio.to_thread(
            requests.post,
            url,
            json={"text": f"GovMap pipeline '{source}' failed: {detail or 'unknown error'}"},
            timeout=10,
        )
    except Exception:
        logger.warning("alert webhook failed for source %s", source)


async def record_run(
    source: str, record_count: int, status: str, detail: str | None = None
) -> None:
    """Upsert one pipeline_status row. last_run always advances; last_success
    only advances on an ok run, so a later failure doesn't erase when the
    source was last known good."""
    now = datetime.now(timezone.utc)
    values: dict = {
        "source": source,
        "last_run": now,
        "record_count": record_count,
        "status": status,
        "detail": detail,
    }
    if status == "ok":
        values["last_success"] = now

    async with async_session_factory() as session:
        stmt = pg_insert(PipelineStatusRow).values(**values)
        update = {k: getattr(stmt.excluded, k) for k in values if k != "source"}
        stmt = stmt.on_conflict_do_update(
            index_elements=[PipelineStatusRow.source], set_=update
        )
        await session.execute(stmt)
        await session.commit()

    if status == "error":
        await _maybe_alert(source, detail)
