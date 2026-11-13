"""Layer 1 pipeline: complete, bounded OpenFEC Election Dates snapshot."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.config import settings
from app.pipelines.batch import BatchResult
from app.pipelines.fec_finance import _fec_get
from app.pipelines.staging import write_json_atomic
from app.schemas.election import FecCalendarPageRaw, FecCalendarSnapshotRaw

logger = logging.getLogger(__name__)

SOURCE_NAME = "fec_election_calendar"
STAGING_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "staging" / "fec_election_calendar_raw.json"
)

_PAGE_SIZE = 100
_MAX_PAGES = 10
_PAGE_PAUSE_SECONDS = 0.1
_ELECTION_DATE_CATEGORY_ID = 36


class CalendarSnapshotIncompleteError(RuntimeError):
    """OpenFEC did not provide evidence for a complete calendar-year snapshot."""


def _required_int(pagination: dict[str, object], key: str) -> int:
    value = pagination.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CalendarSnapshotIncompleteError(
            f"OpenFEC election calendar pagination {key!r} is malformed"
        )
    return value


def run(calendar_year: int | None = None) -> BatchResult:
    """Fetch one exact-count election-date year; never stage an incomplete walk."""
    if not settings.fec_api_key:
        raise RuntimeError("FEC_API_KEY is not set — required for the election calendar")

    year = calendar_year if calendar_year is not None else settings.fec_cycle
    if not 1979 <= year <= 2100:
        raise ValueError("election calendar year must be between 1979 and 2100")
    candidates = []
    seen_ids: set[int] = set()
    expected_count: int | None = None
    expected_pages: int | None = None
    page_count = 0

    for page_number in range(1, _MAX_PAGES + 1):
        if page_number > 1:
            time.sleep(_PAGE_PAUSE_SECONDS)
        payload = _fec_get(
            "calendar-dates",
            calendar_category_id=_ELECTION_DATE_CATEGORY_ID,
            min_start_date=f"{year}-01-01",
            max_start_date=f"{year}-12-31",
            sort="start_date",
            page=page_number,
            per_page=_PAGE_SIZE,
        )
        try:
            page = FecCalendarPageRaw.model_validate(payload)
        except ValidationError as exc:
            raise CalendarSnapshotIncompleteError(
                f"OpenFEC calendar page {page_number} has an invalid shape"
            ) from exc

        pagination = page.pagination
        count = _required_int(pagination, "count")
        pages = _required_int(pagination, "pages")
        if pagination.get("is_count_exact") is not True:
            raise CalendarSnapshotIncompleteError(
                "OpenFEC did not mark the election calendar count exact"
            )
        if pages < 1 or pages > _MAX_PAGES:
            raise CalendarSnapshotIncompleteError(
                f"OpenFEC election calendar page count is outside 1..{_MAX_PAGES}"
            )
        if expected_count is None:
            expected_count = count
            expected_pages = pages
        elif count != expected_count or pages != expected_pages:
            raise CalendarSnapshotIncompleteError(
                "OpenFEC election calendar pagination changed during the page walk"
            )

        page_count = page_number
        if len(page.results) > _PAGE_SIZE or (
            page_number < pages and len(page.results) != _PAGE_SIZE
        ):
            raise CalendarSnapshotIncompleteError(
                f"OpenFEC election calendar page {page_number} has an unexpected result count"
            )
        for event in page.results:
            if event.start_date.year != year:
                raise CalendarSnapshotIncompleteError(
                    "OpenFEC returned an election date outside the requested calendar year"
                )
            if event.event_id in seen_ids:
                raise CalendarSnapshotIncompleteError(
                    "OpenFEC election calendar event IDs repeated during pagination"
                )
            seen_ids.add(event.event_id)
            candidates.append(event)

        if page_number == pages:
            break
    else:
        raise CalendarSnapshotIncompleteError(
            f"OpenFEC election calendar exceeded {_MAX_PAGES} pages"
        )

    if expected_count is None or expected_pages is None:
        raise CalendarSnapshotIncompleteError("OpenFEC returned no election calendar pages")
    if expected_count == 0 or len(candidates) != expected_count:
        raise CalendarSnapshotIncompleteError(
            "OpenFEC election calendar result count did not match its exact count"
        )

    event_rows = [
        event.model_dump(mode="json")
        for event in sorted(candidates, key=lambda row: (row.start_date, row.event_id))
    ]
    revision = hashlib.sha256(
        json.dumps(event_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    snapshot = FecCalendarSnapshotRaw(
        source=SOURCE_NAME,
        calendar_year=year,
        complete=True,
        expected_count=expected_count,
        page_count=page_count,
        snapshot_revision=revision,
        fetched_at=datetime.now(UTC),
        events=event_rows,
    )
    write_json_atomic(STAGING_PATH, snapshot.model_dump(mode="json"), indent=2)

    logger.info(
        "%s: staged %d election dates for %d across %d page(s)",
        SOURCE_NAME,
        len(event_rows),
        year,
        page_count,
    )
    return BatchResult(total=len(event_rows), succeeded=len(event_rows), failed=0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
