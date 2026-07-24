"""Layer 1 pipeline: committee meetings from the Congress.gov v3 API.

For each chamber, pulls the most-recently-updated committee meetings (event ids
via the list endpoint) and fetches each meeting's detail — committee(s), date,
title, location, related bills — staging one flat row per meeting. Bounded per
chamber (committee_meetings_limit). Reuses the Congress.gov session/retry/header
helper from congress_gov_bills (the key is an X-Api-Key HEADER, never a URL
param). Self-diagnosing: logs the keys of the first detail payload so a field
mismatch is visible in the deploy logs.

Run directly: `python -m app.pipelines.congress_committee_meetings`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from app.config import settings
from app.pipelines.congress_gov_bills import _PAGE, _get
from app.schemas.committee import CommitteeMeetingRaw

logger = logging.getLogger(__name__)

SOURCE_NAME = "congress_committee_meetings"

# backend/app/pipelines/congress_committee_meetings.py -> parents[2] == backend/
STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING_PATH = STAGING_DIR / "committee_meetings_raw.json"

_CHAMBERS = ("house", "senate")
_LIST_MAX_PAGES = 8  # safety bound on list pagination per chamber


def _event_ids(congress: int, chamber: str, cap: int) -> list[str]:
    """Most-recently-updated meeting event ids for the chamber, newest first."""
    ids: list[str] = []
    offset = 0
    for _ in range(_LIST_MAX_PAGES):
        if len(ids) >= cap:
            break
        data = _get(
            f"committee-meeting/{congress}/{chamber}",
            sort="updateDate desc",
            limit=_PAGE,
            offset=offset,
        )
        items = data.get("committeeMeetings", []) or []
        if offset == 0:
            # Surface the real list key if our assumption is wrong (no items).
            logger.info(
                "committee_meetings %s list keys=%s; items=%d",
                chamber, sorted(data.keys()), len(items),
            )
        if not items:
            break
        for it in items:
            ev = it.get("eventId")
            if ev:
                ids.append(str(ev))
        if not data.get("pagination", {}).get("next"):
            break
        offset += _PAGE
    return ids[:cap]


def _meeting_row(congress: int, chamber: str, event_id: str, logged: list[bool]) -> dict | None:
    data = _get(f"committee-meeting/{congress}/{chamber}/{event_id}")
    detail = data.get("committeeMeeting")
    if not detail:
        return None
    if not logged[0]:
        logger.info("committee_meetings first-detail keys: %s", sorted(detail.keys()))
        logged[0] = True
    try:
        m = CommitteeMeetingRaw.model_validate(detail)
    except ValidationError as exc:
        logger.warning("skipping meeting %s: %s", event_id, exc)
        return None

    system_codes = [c.systemCode for c in m.committees if c.systemCode]
    if not system_codes:
        return None  # can't attribute the meeting to any committee

    location = None
    if m.location:
        parts = [m.location.room, m.location.building, m.location.address]
        location = " · ".join(p for p in parts if p) or None
    bills = [
        {"congress": b.congress, "type": b.type, "number": b.number}
        for b in (m.relatedItems.bills if m.relatedItems else [])
        if b.type and b.number and b.congress
    ]
    return {
        "event_id": m.eventId or event_id,
        "system_codes": system_codes,
        "chamber": m.chamber or chamber.capitalize(),
        "title": m.title,
        "meeting_type": m.type,
        "status": m.meetingStatus,
        "date": m.date.isoformat() if m.date else None,
        "location": location,
        "bills": bills,
    }


def run() -> int:
    if not settings.congress_gov_api_key:
        raise RuntimeError("CONGRESS_GOV_API_KEY is not set — required for committee meetings")
    congress = settings.congress_number
    cap = settings.committee_meetings_limit

    rows: list[dict] = []
    logged = [False]
    for chamber in _CHAMBERS:
        try:
            ids = _event_ids(congress, chamber, cap)
        except Exception as exc:
            logger.warning("committee_meetings: list failed for %s: %s", chamber, exc)
            continue
        for ev in ids:
            try:
                row = _meeting_row(congress, chamber, ev, logged)
                if row:
                    rows.append(row)
            except Exception as exc:
                logger.warning("committee_meetings: detail failed for %s/%s: %s", chamber, ev, exc)

    if not rows:
        raise ValueError("no committee meetings fetched — check the API key and source availability")

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_PATH.write_text(json.dumps(rows))
    logger.info("congress_committee_meetings: staged %d meetings (congress %d)", len(rows), congress)
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
