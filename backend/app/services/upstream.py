"""Durable rolling-hour quotas and process-local outbound concurrency limits."""

from __future__ import annotations

import asyncio
import logging
import math
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Literal

import asyncpg
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.upstream_budget import UpstreamBudget, UpstreamRequest

logger = logging.getLogger(__name__)

Source = Literal["congress", "fec", "govinfo"]
BudgetScope = Literal["shared", "api", "worker"]
WINDOW = timedelta(hours=1)
ADMISSION_TIMEOUT_SECONDS = 5
_budget_engine: AsyncEngine | None = None


class UpstreamCapacityError(Exception):
    message = "request capacity exhausted"

    def __init__(self, source: Source, retry_after: int) -> None:
        self.source = source
        self.retry_after = retry_after
        super().__init__(f"{source} {self.message}")


class UpstreamBudgetUnavailableError(UpstreamCapacityError):
    message = "shared request budget unavailable"


class UpstreamBudgetInitializingError(UpstreamCapacityError):
    message = "shared request budget initializing (one-hour rollout hold)"


class UpstreamUnavailableError(RuntimeError):
    """The upstream timed out, refused the connection, or kept answering 429/5xx.

    Distinct from a per-item failure (404, bad payload): it says the source itself
    is unhealthy, so batch loops stop early and refresh runs don't retry it."""

    def __init__(self, source: Source, detail: str) -> None:
        self.source = source
        super().__init__(f"{source} unavailable: {detail}")


class _Budget:
    def __init__(self, source: Source, concurrent_limit: int) -> None:
        self.source = source
        self.concurrent_limit = concurrent_limit
        self._active = 0
        self._lock = threading.Lock()

    @contextmanager
    def slot(self) -> Iterator[None]:
        with self._lock:
            if self._active >= self.concurrent_limit:
                raise UpstreamCapacityError(self.source, 1)
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1


_LIMITS: dict[Source, int] = {
    "congress": settings.congress_requests_per_hour,
    "fec": settings.fec_requests_per_hour,
    "govinfo": settings.govinfo_requests_per_hour,
}
_TOTAL_LIMITS: dict[Source, int] = {
    "congress": settings.total_congress_requests_per_hour,
    "fec": settings.total_fec_requests_per_hour,
    "govinfo": settings.total_govinfo_requests_per_hour,
}
_BUDGETS = {
    source: _Budget(source, settings.upstream_max_concurrent_requests)
    for source in _LIMITS
}
_PUBLIC_OPERATIONS = threading.BoundedSemaphore(settings.upstream_max_concurrent_requests)


def _engine() -> AsyncEngine:
    global _budget_engine
    if _budget_engine is None:
        # Sync HTTP clients call asyncio.run from worker threads. No pooled
        # connection may be reused across those threads' event loops.
        _budget_engine = create_async_engine(
            settings.database_url,
            poolclass=NullPool,
            connect_args={
                "timeout": 3,
                "command_timeout": 3,
                "server_settings": {"lock_timeout": "2s", "statement_timeout": "3s"},
            },
        )
    return _budget_engine


async def reserve_request(
    source: Source,
    scope: BudgetScope,
    hourly_limit: int,
    total_limit: int,
    db_engine: AsyncEngine | None = None,
) -> None:
    """Commit admission before HTTP starts. Fail closed if usage is unknown."""
    retry_after = 0
    initializing = False
    try:
        async with asyncio.timeout(ADMISSION_TIMEOUT_SECONDS):
            async with (db_engine or _engine()).begin() as conn:
                initialized = (
                    await conn.execute(
                        select(UpstreamBudget.initialized_at)
                        .where(UpstreamBudget.source == source)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if initialized is None:
                    logger.error("%s shared request budget has no initialized source row", source)
                    raise UpstreamBudgetUnavailableError(source, 5)
                now = (await conn.execute(select(func.clock_timestamp()))).scalar_one()
                cutoff = now - WINDOW
                if initialized > cutoff:
                    initializing = True
                    retry_after = max(1, math.ceil((initialized + WINDOW - now).total_seconds()))
                else:
                    matching_source = UpstreamRequest.source == source
                    matching_scope = matching_source & (UpstreamRequest.scope == scope)
                    await conn.execute(
                        delete(UpstreamRequest).where(
                            matching_source, UpstreamRequest.started_at <= cutoff
                        )
                    )
                    total, scoped = (
                        await conn.execute(
                            select(
                                func.count(UpstreamRequest.id),
                                func.count(UpstreamRequest.id).filter(UpstreamRequest.scope == scope),
                            ).where(matching_source)
                        )
                    ).one()
                    for count, limit, predicate in (
                        (total, total_limit, matching_source),
                        (scoped, hourly_limit, matching_scope),
                    ):
                        if count >= limit:
                            expires = (
                                await conn.execute(
                                    select(UpstreamRequest.started_at)
                                    .where(predicate)
                                    .order_by(UpstreamRequest.started_at, UpstreamRequest.id)
                                    .offset(count - limit)
                                    .limit(1)
                                )
                            ).scalar_one() + WINDOW
                            retry_after = max(
                                retry_after, 1, math.ceil((expires - now).total_seconds())
                            )
                    if not retry_after:
                        await conn.execute(
                            insert(UpstreamRequest).values(source=source, scope=scope, started_at=now)
                        )
    except (asyncpg.PostgresError, SQLAlchemyError, TimeoutError, OSError) as exc:
        # Driver errors can contain database credentials. No in-memory fallback.
        logger.warning("%s shared request budget unavailable (%s)", source, type(exc).__name__)
        raise UpstreamBudgetUnavailableError(source, 5) from None
    if retry_after:
        if initializing:
            raise UpstreamBudgetInitializingError(source, retry_after)
        raise UpstreamCapacityError(source, retry_after)


@contextmanager
def request_slot(source: Source) -> Iterator[None]:
    try:
        with _BUDGETS[source].slot():
            asyncio.run(
                reserve_request(
                    source, settings.upstream_budget_scope, _LIMITS[source], _TOTAL_LIMITS[source]
                )
            )
            yield
    except UpstreamCapacityError as exc:
        logger.warning("%s; retry after %ds", exc, exc.retry_after)
        raise


async def run_upstream[**P, T](
    source: Source, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    if not _PUBLIC_OPERATIONS.acquire(blocking=False):
        logger.warning("%s public upstream work capacity exhausted", source)
        raise UpstreamCapacityError(source, 1)
    task = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))

    def release(completed: asyncio.Task[T]) -> None:
        _PUBLIC_OPERATIONS.release()
        if not completed.cancelled():
            completed.exception()

    task.add_done_callback(release)
    # A canceled HTTP request must not free capacity while its worker still runs.
    return await asyncio.shield(task)
