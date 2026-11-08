"""Outage handling shared by the per-item upstream batch loops.

The Congress.gov batch pipelines fetch hundreds of items one at a time and skip
an item that fails. Without a stop condition, an upstream slowdown costs a full
request timeout per remaining item — a 250-bill pull once ran for over two hours
during a Congress.gov read-timeout storm. OutageBreaker ends a loop once the
source looks down, and BatchResult lets the refresh layer record a degraded run
as 'partial' instead of 'ok'.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.upstream import UpstreamUnavailableError

# A run whose failures stay at or under this share of its items is still 'ok'
# (an isolated bad item shouldn't freeze last_success); above it is 'partial'.
_MAX_OK_FAILURE_RATIO = 0.1


class OutageBreaker:
    """Trips after `threshold` consecutive UpstreamUnavailableErrors. Any other
    outcome — a success, or an item-level failure such as a 404 or a bad payload —
    proves the upstream is answering and resets the count."""

    def __init__(self, threshold: int) -> None:
        if threshold < 1:
            raise ValueError("threshold must be at least 1")
        self.threshold = threshold
        self.consecutive = 0

    def success(self) -> None:
        self.consecutive = 0

    def failure(self, exc: BaseException) -> bool:
        """Record a failed item; True once the breaker has tripped."""
        if isinstance(exc, UpstreamUnavailableError):
            self.consecutive += 1
        else:
            self.consecutive = 0
        return self.tripped

    @property
    def tripped(self) -> bool:
        return self.consecutive >= self.threshold

    @property
    def reason(self) -> str:
        return f"upstream unavailable for {self.consecutive} consecutive items"


@dataclass(frozen=True)
class BatchResult:
    """Outcome of one batch pull, counted in work items (bills, members, meetings)."""

    total: int
    succeeded: int
    failed: int
    stopped: str | None = None

    @property
    def degraded(self) -> bool:
        return self.stopped is not None or self.failed > self.total * _MAX_OK_FAILURE_RATIO

    def describe(self, noun: str) -> str | None:
        """Status detail for pipeline_status; None when nothing went wrong."""
        if not self.failed and self.stopped is None:
            return None
        text = f"{self.failed} of {self.total} {noun} failed"
        if self.stopped is not None:
            skipped = self.total - self.succeeded - self.failed
            text += f"; stopped early ({self.stopped}) with {skipped} not attempted"
        return text
