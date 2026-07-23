"""In-process job scheduler.

Runs each source's refresh on its cadence via APScheduler, inside the FastAPI
process. Single uvicorn worker = single scheduler instance, which is the current
deployment; revisit if the API ever scales to multiple workers (jobs would then
need a shared lock so they don't run N times).

Cadences follow the planning-doc cadence table. Add a source by registering its
refresh coroutine (from app.pipelines.refresh) in JOBS with a trigger.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.pipelines.refresh import refresh_members

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

# (job id, coroutine, APScheduler trigger kwargs).
JOBS: list[tuple[str, Callable[[], Awaitable[None]], dict]] = [
    # Members change rarely (new member sworn in, resignation) — weekly is
    # plenty; Sunday 07:00 UTC.
    (
        "refresh_members",
        refresh_members,
        {"trigger": "cron", "day_of_week": "sun", "hour": 7},
    ),
]


def _guarded(
    fn: Callable[[], Awaitable[None]], job_id: str
) -> Callable[[], Awaitable[None]]:
    """A failing job must never take down the scheduler. The refresh_* coroutine
    already records an 'error' status and alerts; this just keeps the loop
    alive and logs."""

    async def wrapper() -> None:
        try:
            await fn()
        except Exception:
            logger.exception("scheduled job %s failed", job_id)

    return wrapper


def start_scheduler() -> None:
    for job_id, fn, trigger in JOBS:
        scheduler.add_job(_guarded(fn, job_id), id=job_id, replace_existing=True, **trigger)
    scheduler.start()
    logger.info("scheduler started with %d job(s)", len(JOBS))


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
