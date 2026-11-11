"""Refresh job scheduler.

Runs each source's refresh on its cadence via APScheduler. On the deployment
platform the scheduled-refresh worker (app.worker) owns it and the API's copy
stays off (SCHEDULER_ENABLED=false on the backend), so exactly one process
schedules refreshes. The legacy single-VM compose still runs it inside the
FastAPI process. Each refresh also holds a per-source Postgres advisory lock
(app.pipelines.runs), so a manual run or a second scheduler can't load the same
source concurrently; the overlapping run is recorded as 'skipped'.

Cadences follow the planning-doc cadence table. Add a source by registering its
tracked refresher (app.pipelines.refresh.REFRESHERS) in JOBS with a trigger.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.pipelines.refresh import REFRESHERS
from app.pipelines.runs import RunSkippedError, run_trigger

logger = logging.getLogger(__name__)

# Explicit so a library default change can't alter refresh behavior. One
# instance per job: an overrunning refresh is skipped, never stacked. Missed
# fires collapse into one run. APScheduler's 1-second default grace would
# silently drop a daily cron whenever the event loop is briefly busy at fire
# time; 15 minutes still runs it, late.
JOB_DEFAULTS = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 15 * 60}


def new_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler(timezone="UTC", job_defaults=JOB_DEFAULTS)


scheduler = new_scheduler()

# Tasks of the scheduled refreshes in flight, so a stopping worker can let them
# record their outcome and release their locks before it exits.
_running_jobs: set[asyncio.Task[Any]] = set()

# (job id, coroutine, APScheduler trigger kwargs).
JOBS: list[tuple[str, Callable[[], Awaitable[None]], dict]] = [
    # Members change rarely, but special elections fill vacant House seats
    # mid-cycle and we want those reflected within a day, not up to a week —
    # daily at 07:00 UTC. It's a single cheap GitHub raw-file fetch, so daily is
    # nearly free; the deploy-time core refresh keeps it warm on top of this.
    (
        "refresh_members",
        REFRESHERS["members"],
        {"trigger": "cron", "hour": 7},
    ),
    # Bills move constantly while Congress is in session. Every 30 min keeps the
    # "what's moving" view fresh; upserts are idempotent when nothing changed.
    (
        "refresh_bills",
        REFRESHERS["bills"],
        {"trigger": "interval", "minutes": 30},
    ),
    # Roll-call votes post throughout session days — 30-min interval catches
    # them promptly; upserts are idempotent when nothing new landed.
    (
        "refresh_votes",
        REFRESHERS["votes"],
        {"trigger": "interval", "minutes": 30},
    ),
    # Per-member sponsored legislation is ~537 API calls; members introduce
    # bills throughout the day but hourly is overkill — daily at 08:00 UTC.
    (
        "refresh_sponsored_bills",
        REFRESHERS["sponsored_bills"],
        {"trigger": "cron", "hour": 8},
    ),
    # Campaign-finance filings post on FEC monthly/quarterly schedules — daily
    # at 09:00 UTC is plenty and keeps the ~537 FEC calls off the hot path.
    (
        "refresh_finance",
        REFRESHERS["finance"],
        {"trigger": "cron", "hour": 9},
    ),
    # ZIP→district crosswalk only changes on redistricting — monthly (1st,
    # 06:00 UTC) is generous. The deploy-time refresh_all keeps it warm too.
    (
        "refresh_zip_districts",
        REFRESHERS["zip_districts"],
        {"trigger": "cron", "day": 1, "hour": 6},
    ),
    # Committee meetings post a few days out and change (postpone/cancel) — twice
    # daily (06:30 / 18:30 UTC) keeps "upcoming meetings" fresh without a heavy
    # per-run detail burst competing with the bills jobs on the hour.
    (
        "refresh_committee_meetings",
        REFRESHERS["committee_meetings"],
        {"trigger": "cron", "hour": "6,18", "minute": 30},
    ),
    # Rolling enrichment of the ~17k sponsored-legislation stub bills — a bounded
    # batch each run, at :15/:45 so it interleaves with refresh_bills (:00/:30)
    # and the two never collide on the Congress.gov hourly budget.
    (
        "refresh_backfill_bills",
        REFRESHERS["backfill_bills"],
        {"trigger": "cron", "minute": "15,45"},
    ),
]


def _guarded(
    fn: Callable[[], Awaitable[None]], job_id: str
) -> Callable[[], Awaitable[None]]:
    """A failing job must never take down the scheduler. The refresh_* coroutine
    already records an 'error' status and alerts; this just keeps the loop
    alive and logs. Runs started here are recorded with trigger 'schedule'."""

    async def wrapper() -> None:
        task = asyncio.current_task()
        if task is not None:
            _running_jobs.add(task)
        token = run_trigger.set("schedule")
        try:
            await fn()
        except RunSkippedError as exc:
            logger.warning("scheduled job %s skipped: %s", job_id, exc)
        except Exception:
            logger.exception("scheduled job %s failed", job_id)
        finally:
            run_trigger.reset(token)
            if task is not None:
                _running_jobs.discard(task)

    return wrapper


def start_scheduler() -> None:
    for job_id, fn, trigger in JOBS:
        scheduler.add_job(_guarded(fn, job_id), id=job_id, replace_existing=True, **trigger)
    scheduler.start()
    logger.info("scheduler started with %d job(s)", len(JOBS))


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


async def stop_scheduler_and_wait(timeout: float) -> None:
    """Stop scheduling and wait up to `timeout` seconds for the refreshes in
    flight to finish. AsyncIOScheduler.shutdown runs on the next loop iteration
    and cancels each running job once; they are not cancelled again here, as a
    second cancellation would interrupt the cleanup that records the run's
    outcome and releases its advisory lock."""
    jobs = {task for task in _running_jobs if not task.done()}
    stop_scheduler()
    if not jobs:
        await asyncio.sleep(0)  # let the deferred shutdown run
        return
    logger.info("waiting up to %ss for %d running refresh(es) to stop", timeout, len(jobs))
    _, pending = await asyncio.wait(jobs, timeout=timeout)
    if pending:
        logger.warning("%d refresh(es) did not stop within %ss", len(pending), timeout)
