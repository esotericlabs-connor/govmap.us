"""Source-run history: one source_runs row per refresh attempt.

`tracked(source, fn)` wraps a refresh coroutine. While it runs it holds a
Postgres advisory lock for the source on its own connection, so a manual
`docker exec` refresh and the in-process scheduler can't load the same source
at the same time. The lock is released if that connection dies, so a crashed
run never leaves it stuck.

A run that can't take the lock is recorded as 'skipped' and raises
RunSkippedError. Once the lock is held, any row of this source still marked
'running' belongs to a process that died, and is marked 'abandoned'.

record_run() (app.pipelines.status) reports each refresh's outcome here
through note_outcome(); batch pulls add item counts through note_batch().
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Integer, cast, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.source_run import SourceRun
from app.pipelines.batch import BatchResult
from app.sources import SOURCES

logger = logging.getLogger(__name__)

RETENTION = timedelta(days=400)
FINAL_OUTCOMES = frozenset({"ok", "partial", "error"})

# First key of the two-key advisory lock, so these locks can't collide with any
# other advisory lock use. The second key is derived from the source name.
_LOCK_NAMESPACE = 0x474D5352
_DETAIL_LIMIT = 4000

run_trigger: ContextVar[str] = ContextVar("run_trigger", default="manual")


@dataclass
class _ActiveRun:
    source: str
    run_id: int
    outcome: str | None = None
    record_count: int | None = None
    detail: str | None = None
    batch: BatchResult | None = None


_active: ContextVar[_ActiveRun | None] = ContextVar("active_source_run", default=None)


class RunSkippedError(RuntimeError):
    """Another run of the same source holds its lock; this one did nothing."""


def current_run_id() -> int | None:
    run = _active.get()
    return run.run_id if run else None


def note_outcome(source: str, record_count: int, status: str, detail: str | None) -> None:
    run = _active.get()
    if run is not None and run.source == source:
        run.outcome = status
        run.record_count = record_count
        run.detail = detail


def note_batch(source: str, result: BatchResult) -> None:
    run = _active.get()
    if run is not None and run.source == source:
        run.batch = result


_SECRET_PARAM = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret)=[^&\s\"']+"
)
_BEARER = re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9._~+/=-]{8,}")
_URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/@\s]+@")


def redact(text: str | None) -> str | None:
    """Remove credentials from text bound for the database or an alert. Upstream
    error messages can quote request URLs or headers."""
    if text is None:
        return None
    for secret in (
        settings.congress_gov_api_key,
        settings.fec_api_key,
        settings.hud_api_token,
        settings.internal_password,
        settings.alert_webhook_url,
    ):
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
    text = _SECRET_PARAM.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    text = _BEARER.sub(lambda m: f"{m.group(1)} [REDACTED]", text)
    text = _URL_USERINFO.sub(lambda m: f"{m.group(1)}[REDACTED]@", text)
    if len(text) > _DETAIL_LIMIT:
        text = text[:_DETAIL_LIMIT] + "…"
    return text


def _lock_key(source: str) -> int:
    return int.from_bytes(hashlib.sha256(source.encode()).digest()[:4], "big", signed=True)


def _lock_args(source: str) -> tuple:
    return (cast(_LOCK_NAMESPACE, Integer), cast(_lock_key(source), Integer))


def input_manifest(paths: tuple[Path, ...]) -> list[dict]:
    """Hash each staging file, so a run's row shows exactly which inputs it
    loaded, and modified_at shows a file left over from an earlier pull."""
    manifest: list[dict] = []
    for path in paths:
        try:
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as handle:
                stat = path.stat()
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
                    size += len(chunk)
        except FileNotFoundError:
            manifest.append({"name": path.name, "sha256": None, "bytes": None, "modified_at": None})
            continue
        manifest.append(
            {
                "name": path.name,
                "sha256": digest.hexdigest(),
                "bytes": size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            }
        )
    return manifest


def final_outcome(run: _ActiveRun, error: BaseException | None) -> tuple[str, str | None]:
    """The outcome to store. A refresh that raised after recording 'partial'
    (an incomplete vote batch, a withheld roster change) stays 'partial'."""
    outcome, detail = run.outcome, run.detail
    if outcome is not None and outcome not in FINAL_OUTCOMES:
        return "error", f"unexpected status {outcome!r}: {detail or ''}".rstrip(": ")
    if error is not None and outcome in (None, "ok"):
        return "error", detail or f"{type(error).__name__}: {error}"
    if outcome is None:
        return "error", "no outcome recorded"
    return outcome, detail


_lock_engine: AsyncEngine | None = None


def _engine() -> AsyncEngine:
    # A separate, unpooled engine: a lock connection is held for a whole run
    # and must not take a slot from the pool that serves API requests.
    global _lock_engine
    if _lock_engine is None:
        _lock_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    return _lock_engine


def _code_version() -> str | None:
    sha = settings.app_commit_sha
    return None if sha == "unknown" else sha


class TrackedRefresh:
    """A refresh coroutine wrapped with locking and run history."""

    def __init__(self, source: str, fn: Callable[[], Awaitable[None]]) -> None:
        if source not in SOURCES:
            raise ValueError(f"source {source!r} is not in app.sources.SOURCES")
        self.source = source
        self.fn = fn

    def __repr__(self) -> str:
        return f"TrackedRefresh({self.source!r})"

    async def __call__(self) -> None:
        async with _engine().connect() as conn:
            locked = (
                await conn.execute(select(func.pg_try_advisory_lock(*_lock_args(self.source))))
            ).scalar_one()
            await conn.commit()
            if not locked:
                await conn.execute(
                    insert(SourceRun).values(
                        source=self.source,
                        trigger=run_trigger.get(),
                        code_version=_code_version(),
                        outcome="skipped",
                        finished_at=func.now(),
                        detail="another run of this source was in progress",
                    )
                )
                await conn.commit()
                raise RunSkippedError(f"{self.source}: another run is in progress")
            try:
                await self._run_locked(conn)
            finally:
                await self._unlock(conn)

    async def _run_locked(self, conn: AsyncConnection) -> None:
        await conn.execute(
            update(SourceRun)
            .where(SourceRun.source == self.source, SourceRun.outcome == "running")
            .values(
                outcome="abandoned",
                finished_at=func.now(),
                detail="the process running it ended before it finished",
            )
        )
        run_id = (
            await conn.execute(
                insert(SourceRun)
                .values(
                    source=self.source,
                    trigger=run_trigger.get(),
                    code_version=_code_version(),
                    outcome="running",
                )
                .returning(SourceRun.id)
            )
        ).scalar_one()
        await conn.commit()

        run = _ActiveRun(source=self.source, run_id=run_id)
        token = _active.set(run)
        error: BaseException | None = None
        try:
            await self.fn()
        except BaseException as exc:
            error = exc
            raise
        finally:
            _active.reset(token)
            try:
                await self._finish(conn, run, error)
            except Exception:
                logger.exception("source run %s/%d: could not record its outcome", self.source, run_id)
                if conn.in_transaction():
                    await conn.rollback()

    async def _finish(
        self, conn: AsyncConnection, run: _ActiveRun, error: BaseException | None
    ) -> None:
        outcome, detail = final_outcome(run, error)
        staging = SOURCES[self.source].staging_files
        inputs = None
        if outcome in ("ok", "partial") and staging:
            inputs = await asyncio.to_thread(input_manifest, staging)
        batch = run.batch
        await conn.execute(
            update(SourceRun)
            .where(SourceRun.id == run.run_id)
            .values(
                finished_at=func.now(),
                outcome=outcome,
                record_count=run.record_count,
                items_total=batch.total if batch else None,
                items_succeeded=batch.succeeded if batch else None,
                items_failed=batch.failed if batch else None,
                inputs=inputs,
                detail=redact(detail),
            )
        )
        await conn.execute(
            delete(SourceRun).where(
                SourceRun.source == self.source,
                SourceRun.started_at < datetime.now(UTC) - RETENTION,
            )
        )
        await conn.commit()

    async def _unlock(self, conn: AsyncConnection) -> None:
        try:
            if conn.in_transaction():
                await conn.rollback()
            await conn.execute(select(func.pg_advisory_unlock(*_lock_args(self.source))))
            await conn.commit()
        except Exception:
            # Closing the connection releases the lock server-side.
            logger.warning("source run %s: advisory unlock failed", self.source, exc_info=True)
            await conn.invalidate()


def tracked(source: str, fn: Callable[[], Awaitable[None]]) -> TrackedRefresh:
    return TrackedRefresh(source, fn)
