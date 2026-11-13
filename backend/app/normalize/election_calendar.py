"""Layer 2 normalizer: complete OpenFEC election-calendar snapshot -> Postgres."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_factory
from app.models.election import ElectionCalendarCoverage, ElectionCalendarEvent
from app.schemas.election import FecCalendarEventRaw, FecCalendarSnapshotRaw

logger = logging.getLogger(__name__)

STAGING_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "staging" / "fec_election_calendar_raw.json"
)
_CHUNK = 500


def _event_row(calendar_year: int, event: FecCalendarEventRaw) -> dict[str, object]:
    return {
        "calendar_year": calendar_year,
        "event_id": event.event_id,
        "category": event.category,
        "summary": event.summary,
        "description": event.description,
        "location": event.location,
        "state": event.state or [],
        "start_date": event.start_date,
        "end_date": event.end_date,
        "url": str(event.url) if event.url is not None else None,
    }


async def load_calendar() -> int:
    if not STAGING_PATH.exists():
        raise FileNotFoundError(
            f"no election calendar staging data at {STAGING_PATH} — "
            "run the fec_election_calendar pipeline first"
        )

    try:
        staged = FecCalendarSnapshotRaw.model_validate_json(
            STAGING_PATH.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise ValueError("election calendar staging snapshot is invalid") from exc

    if staged.source != "fec_election_calendar" or not staged.complete:
        raise ValueError("refusing to load an election calendar snapshot not marked complete")
    if staged.expected_count != len(staged.events) or not staged.events:
        raise ValueError("election calendar staging count does not match the complete snapshot")
    event_ids = [event.event_id for event in staged.events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("election calendar staging snapshot contains duplicate FEC event IDs")
    if any(event.start_date.year != staged.calendar_year for event in staged.events):
        raise ValueError("election calendar staging snapshot contains an event from another year")

    rows = [_event_row(staged.calendar_year, event) for event in staged.events]
    coverage = {
        "calendar_year": staged.calendar_year,
        "complete": True,
        "event_count": len(rows),
        "expected_count": staged.expected_count,
        "page_count": staged.page_count,
        "snapshot_revision": staged.snapshot_revision,
        "fetched_at": staged.fetched_at,
    }

    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                delete(ElectionCalendarEvent).where(
                    ElectionCalendarEvent.calendar_year == staged.calendar_year
                )
            )
            for start in range(0, len(rows), _CHUNK):
                await session.execute(
                    pg_insert(ElectionCalendarEvent).values(rows[start : start + _CHUNK])
                )
            stmt = pg_insert(ElectionCalendarCoverage).values(coverage)
            stmt = stmt.on_conflict_do_update(
                index_elements=[ElectionCalendarCoverage.calendar_year],
                set_={
                    key: getattr(stmt.excluded, key)
                    for key in coverage
                    if key != "calendar_year"
                },
            )
            await session.execute(stmt)

    logger.info(
        "elections: atomically replaced %d FEC election dates for %d",
        len(rows),
        staged.calendar_year,
    )
    return len(rows)


if __name__ == "__main__":
    asyncio.run(load_calendar())
