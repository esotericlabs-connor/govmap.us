"""Scheduled-refresh worker.

    python -m app.worker

Runs the source refresh schedule (app.scheduler) in its own container, apart
from the API, so a long pull never competes with request handling for the
event loop, memory or the API's outbound request budget. The backend's own
scheduler stays off (SCHEDULER_ENABLED=false there), so exactly one process
owns the schedule; per-source advisory locks (app.pipelines.runs) still stop a
manual run from overlapping a scheduled one.

The worker never migrates: the backend applies migrations when it starts. With
the scheduler enabled, the worker first waits, bounded, for the database to
reach this image's Alembic head, so no refresh writes to a schema it wasn't
built for; it exits non-zero if that doesn't happen and the restart policy
tries again. With SCHEDULER_ENABLED=false it stays idle and never connects.

While it is working it touches HEARTBEAT_PATH every HEARTBEAT_SECONDS; the
container healthcheck fails once the file is older than
HEARTBEAT_MAX_AGE_SECONDS. SIGTERM/SIGINT stop it cleanly: refreshes in flight
are cancelled and recorded as 'abandoned'.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time
from pathlib import Path

import asyncpg
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app import scheduler as scheduler_module
from app.config import settings
from app.db import engine
from app.logging_setup import WORKER_LOG, setup_file_logging

logger = logging.getLogger("app.worker")

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
# Kept in step with the worker healthcheck in docker-compose.PaaS.yml.
HEARTBEAT_PATH = Path("/tmp/govmap-worker-heartbeat")
HEARTBEAT_SECONDS = 30
HEARTBEAT_MAX_AGE_SECONDS = 120
SCHEMA_WAIT_SECONDS = 300
SCHEMA_POLL_SECONDS = 5
SCHEMA_CHECK_TIMEOUT_SECONDS = 5
# Time for cancelled refreshes to record their outcome; inside the compose
# stop_grace_period.
SHUTDOWN_TIMEOUT_SECONDS = 15
_STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)


def expected_heads() -> set[str]:
    return set(ScriptDirectory(str(MIGRATIONS_DIR)).get_heads())


def _current_heads(connection: Connection) -> set[str]:
    return set(MigrationContext.configure(connection).get_current_heads())


async def database_heads(db_engine: AsyncEngine | None = None) -> set[str]:
    """The revisions recorded in alembic_version; empty if it doesn't exist."""
    async with asyncio.timeout(SCHEMA_CHECK_TIMEOUT_SECONDS):
        async with (db_engine or engine).connect() as conn:
            return await conn.run_sync(_current_heads)


async def _sleep_unless_stopped(stop: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(seconds):
            await stop.wait()


async def wait_for_schema(expected: set[str], stop: asyncio.Event) -> bool:
    """True once the database is at `expected`; False if it isn't within
    SCHEMA_WAIT_SECONDS or a stop is requested first."""
    deadline = time.monotonic() + SCHEMA_WAIT_SECONDS
    target = ", ".join(sorted(expected))
    reported: str | None = None
    while not stop.is_set():
        try:
            current = await database_heads()
        except (asyncpg.PostgresError, SQLAlchemyError, TimeoutError, OSError) as exc:
            # Driver exception messages may contain credentials or host addresses.
            state = f"database unavailable ({type(exc).__name__})"
        else:
            if current == expected:
                logger.info("database schema is at %s", target)
                return True
            state = f"database schema is at {', '.join(sorted(current)) or 'no revision'}"
        if state != reported:
            logger.info("waiting for migrations to %s: %s", target, state)
            reported = state
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.error(
                "database schema did not reach %s within %ds (%s)", target, SCHEMA_WAIT_SECONDS, state
            )
            return False
        await _sleep_unless_stopped(stop, min(SCHEMA_POLL_SECONDS, remaining))
    return False


def _beat() -> None:
    try:
        HEARTBEAT_PATH.touch()
    except OSError as exc:
        logger.warning("could not write the worker heartbeat: %s", exc)


def _clear_heartbeat() -> None:
    # A container restart keeps /tmp; a stale file must not read as healthy.
    try:
        HEARTBEAT_PATH.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("could not remove the worker heartbeat: %s", exc)


async def _serve(stop: asyncio.Event, *, scheduled: bool) -> bool:
    """Heartbeat until a stop is requested. False if the scheduler stopped on
    its own, so the process exits and the restart policy replaces it."""
    while not stop.is_set():
        if scheduled and not scheduler_module.scheduler.running:
            logger.error("the scheduler stopped unexpectedly; exiting so the container restarts")
            return False
        _beat()
        await _sleep_unless_stopped(stop, HEARTBEAT_SECONDS)
    return True


async def run_worker() -> int:
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in _STOP_SIGNALS:
        loop.add_signal_handler(sig, stop.set)
    _clear_heartbeat()
    try:
        logger.info(
            "worker starting (commit %s); shared scope %s hourly request budgets: "
            "congress %d/%d, fec %d/%d, govinfo %d/%d (scope/total)",
            settings.app_commit_sha,
            settings.upstream_budget_scope,
            settings.congress_requests_per_hour,
            settings.total_congress_requests_per_hour,
            settings.fec_requests_per_hour,
            settings.total_fec_requests_per_hour,
            settings.govinfo_requests_per_hour,
            settings.total_govinfo_requests_per_hour,
        )
        if not settings.scheduler_enabled:
            logger.info("scheduled pipeline refreshes disabled (SCHEDULER_ENABLED=false); worker idle")
            await _serve(stop, scheduled=False)
            return 0
        if not await wait_for_schema(expected_heads(), stop):
            return 0 if stop.is_set() else 1
        scheduler_module.start_scheduler()
        try:
            healthy = await _serve(stop, scheduled=True)
        finally:
            await scheduler_module.stop_scheduler_and_wait(SHUTDOWN_TIMEOUT_SECONDS)
        return 0 if healthy else 1
    finally:
        _clear_heartbeat()
        await engine.dispose()
        for sig in _STOP_SIGNALS:
            loop.remove_signal_handler(sig)
        logger.info("worker stopped")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    setup_file_logging(WORKER_LOG)
    return asyncio.run(run_worker())


if __name__ == "__main__":
    raise SystemExit(main())
