"""Layer 2 normalizer: committee-meeting staging -> committee_meetings.

Maps each meeting's Congress.gov systemCode(s) back to our committee_id
(app.committee_codes), drops meetings whose committee we don't hold, and
full-replaces the table (meetings churn and canceled ones should drop). A
meeting shared by a full committee and one of its subcommittees yields a row
under each. Must run after committees exist (FK).

Run directly: `python -m app.normalize.committee_meetings`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.committee_codes import to_committee_id
from app.db import async_session_factory
from app.models.committee import Committee, CommitteeMeeting

logger = logging.getLogger(__name__)

STAGING_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "staging" / "committee_meetings_raw.json"
)

_CHUNK = 1000


def _bill_ids(bills: list[dict]) -> list[str]:
    out: list[str] = []
    for b in bills:
        t, n, c = b.get("type"), b.get("number"), b.get("congress")
        if t and n and c:
            out.append(f"{str(t).lower()}{n}-{c}")
    return out


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def meeting_rows(staged: list[dict], known: set[str]) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    dropped = 0
    for m in staged:
        event_id = m.get("event_id")
        if not event_id:
            continue
        bill_ids = _bill_ids(m.get("bills") or [])
        meeting_dt = _dt(m.get("date"))
        mapped_any = False
        for sc in m.get("system_codes") or []:
            cid = to_committee_id(sc)
            if cid not in known:
                continue
            key = (str(event_id), cid)
            if key in seen:
                continue
            seen.add(key)
            mapped_any = True
            rows.append(
                {
                    "event_id": str(event_id),
                    "committee_id": cid,
                    "chamber": m.get("chamber"),
                    "title": m.get("title"),
                    "meeting_type": m.get("meeting_type"),
                    "status": m.get("status"),
                    "meeting_datetime": meeting_dt,
                    "location": m.get("location"),
                    "bill_ids": bill_ids or None,
                }
            )
        if not mapped_any:
            dropped += 1
    if dropped:
        logger.info("committee_meetings: %d meeting(s) had no known committee (dropped)", dropped)
    return rows


async def load_committee_meetings() -> int:
    if not STAGING_PATH.exists():
        raise FileNotFoundError(
            f"no staging data at {STAGING_PATH} — run the congress_committee_meetings pipeline first"
        )
    staged = json.loads(STAGING_PATH.read_text())

    async with async_session_factory() as session:
        known = set((await session.execute(select(Committee.committee_id))).scalars().all())
        rows = meeting_rows(staged, known)
        # Full replace — meetings churn; a canceled/removed meeting must drop out.
        await session.execute(delete(CommitteeMeeting))
        for i in range(0, len(rows), _CHUNK):
            await session.execute(pg_insert(CommitteeMeeting).values(rows[i : i + _CHUNK]))
        await session.commit()

    logger.info("committee_meetings: loaded %d meeting rows", len(rows))
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(load_committee_meetings())
