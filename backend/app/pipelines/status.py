"""Pipeline run status, persisted to the pipeline_status table.

Replaces the ephemeral pipeline_status.json. Every source records its outcome
here via record_run(), so /internal/pipeline-status survives restarts and the
scheduler can reason about staleness. On failure, optionally fires a webhook.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.db import async_session_factory
from app.models.pipeline_status import PipelineStatusRow

logger = logging.getLogger(__name__)


def _post_alert(url: str, text: str) -> int:
    # Redirects are refused so a misconfigured or hijacked endpoint can't bounce
    # the notification (and the secret-bearing URL's payload) somewhere else.
    # The reply body is never read; streaming keeps it from being downloaded.
    response = requests.post(
        url, json={"text": text}, timeout=10, allow_redirects=False, stream=True
    )
    try:
        return response.status_code
    finally:
        response.close()


async def send_alert(text: str) -> None:
    """POST an operator notification to the alert webhook, if one is configured.

    Used for pipeline failures and other noteworthy data events (e.g. a vacant
    House seat becoming filled). No-op when alert_webhook_url is unset.
    Transport failures and non-2xx answers are logged (by exception class or
    HTTP status only — the webhook URL is a credential and the text may carry
    upstream error details) and never propagate to the caller; programming
    errors do propagate so they aren't silently hidden."""
    url = settings.alert_webhook_url
    if not url:
        return
    try:
        status_code = await asyncio.to_thread(_post_alert, url, text)
    except requests.RequestException as exc:
        logger.warning("alert webhook post failed: %s", type(exc).__name__)
        return
    if not 200 <= status_code < 300:
        logger.warning("alert webhook rejected the notification: HTTP %d", status_code)


async def _maybe_alert(source: str, detail: str | None) -> None:
    await send_alert(f"GovMap pipeline '{source}' failed: {detail or 'unknown error'}")


async def record_run(
    source: str, record_count: int, status: str, detail: str | None = None
) -> None:
    """Upsert one pipeline_status row. last_run always advances; last_success
    only advances on an ok run, so a later failure doesn't erase when the
    source was last known good."""
    now = datetime.now(UTC)
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
