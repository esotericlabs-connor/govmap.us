"""In-process job scheduler.

Runs each source pipeline on its cadence inside the FastAPI process via
APScheduler. Single uvicorn worker = single scheduler instance, which is the
current deployment; revisit if the API ever scales to multiple workers (jobs
would then need a shared lock so they don't run N times).
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.normalize.members import normalize_and_load
from app.pipelines import congress_legislators

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def refresh_members() -> None:
    """Pull congress-legislators, then normalize into Postgres. The pull is
    synchronous (requests), so it runs in a thread to avoid blocking the event
    loop; the normalize step is async. Never raises — a failed run is logged
    and the next scheduled run tries again."""
    logger.info("scheduled members refresh: starting")
    try:
        await asyncio.to_thread(congress_legislators.run)
        await normalize_and_load()
        logger.info("scheduled members refresh: complete")
    except Exception:
        logger.exception("scheduled members refresh failed")


def start_scheduler() -> None:
    # Members change rarely (new member sworn in, resignation, special
    # election), so weekly is plenty — Sunday 07:00 UTC per the cadence table.
    scheduler.add_job(
        refresh_members,
        "cron",
        day_of_week="sun",
        hour=7,
        id="refresh_members",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
