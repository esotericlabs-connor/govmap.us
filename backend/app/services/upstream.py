"""Process-wide outbound budgets shared by public requests and refresh jobs."""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Literal, ParamSpec, TypeVar

from app.config import settings

logger = logging.getLogger(__name__)

Source = Literal["congress", "fec", "govinfo"]
P = ParamSpec("P")
T = TypeVar("T")


class UpstreamCapacityError(Exception):
    def __init__(self, source: Source, retry_after: int) -> None:
        self.source = source
        self.retry_after = retry_after
        super().__init__(f"{source} request capacity exhausted")


class _Budget:
    def __init__(self, source: Source, hourly_limit: int, concurrent_limit: int) -> None:
        self.source = source
        self.hourly_limit = hourly_limit
        self.concurrent_limit = concurrent_limit
        self._started: deque[float] = deque()
        self._active = 0
        self._lock = threading.Lock()

    @contextmanager
    def slot(self) -> Iterator[None]:
        with self._lock:
            now = time.monotonic()
            while self._started and now - self._started[0] >= 3600:
                self._started.popleft()
            if len(self._started) >= self.hourly_limit:
                raise UpstreamCapacityError(
                    self.source, max(1, math.ceil(self._started[0] + 3600 - now))
                )
            if self._active >= self.concurrent_limit:
                raise UpstreamCapacityError(self.source, 1)
            self._started.append(now)
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
_BUDGETS = {
    source: _Budget(source, limit, settings.upstream_max_concurrent_requests)
    for source, limit in _LIMITS.items()
}
_PUBLIC_OPERATIONS = threading.BoundedSemaphore(settings.upstream_max_concurrent_requests)


@contextmanager
def request_slot(source: Source) -> Iterator[None]:
    try:
        with _BUDGETS[source].slot():
            yield
    except UpstreamCapacityError as exc:
        logger.warning("%s; retry after %ds", exc, exc.retry_after)
        raise


async def run_upstream(
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
