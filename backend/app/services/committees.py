"""On-demand committee referred-bills fetch (Pass 1c).

The committee detail page shows a "recent bills before this committee" section.
Rather than mirror committee→bill referrals, we fetch them lazily from
Congress.gov on view and join our own `bills` for titles. Fail-soft: the section
just omits on any error, a joint committee (ambiguous systemCode chamber), or
without a Congress.gov key. Self-diagnosing: logs the first item's keys so a
field-name mismatch is visible in the logs.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.committee_codes import to_system_code
from app.config import settings
from app.models.bill import Bill
from app.models.committee import Committee
from app.pipelines.congress_gov_bills import _get

logger = logging.getLogger(__name__)


async def referred_bills(db: AsyncSession, committee_id: str, limit: int = 15) -> list[dict]:
    """Recent bills referred to the committee, newest first, enriched with our
    stored title/latest_action where we hold the bill."""
    if not settings.congress_gov_api_key:
        return []
    committee = (
        await db.execute(select(Committee.chamber).where(Committee.committee_id == committee_id))
    ).first()
    if committee is None or committee.chamber not in ("house", "senate"):
        return []  # unknown, or a joint committee (systemCode chamber is ambiguous)

    system_code = to_system_code(committee_id)
    congress = settings.congress_number
    try:
        data = await asyncio.to_thread(
            _get, f"committee/{congress}/{committee.chamber}/{system_code}/bills", limit=limit
        )
    except Exception as exc:
        logger.warning("referred_bills: fetch failed for %s: %s", committee_id, exc)
        return []

    container = data.get("committee-bills")
    items = container.get("bills") if isinstance(container, dict) else None
    if items is None:
        items = data.get("bills") or []
    if items:
        logger.info("referred_bills first-item keys for %s: %s", committee_id, sorted(items[0].keys()))

    parsed: list[dict] = []
    seen: set[str] = set()
    for it in items:
        btype = it.get("billType") or it.get("type")
        number = it.get("billNumber") or it.get("number")
        bcong = it.get("congress") or congress
        if not btype or number in (None, ""):
            continue
        bill_id = f"{str(btype).lower()}{number}-{bcong}"
        if bill_id in seen:
            continue
        seen.add(bill_id)
        parsed.append(
            {
                "bill_id": bill_id,
                "bill_type": str(btype).lower(),
                "number": number,
                "relationship": it.get("relationshipType"),
                "title": None,
                "latest_action": None,
            }
        )
        if len(parsed) >= limit:
            break
    if not parsed:
        return []

    rows = (
        await db.execute(
            select(Bill.bill_id, Bill.title, Bill.latest_action).where(
                Bill.bill_id.in_([p["bill_id"] for p in parsed])
            )
        )
    ).all()
    by_id = {r.bill_id: r for r in rows}
    for p in parsed:
        r = by_id.get(p["bill_id"])
        if r:
            p["title"] = r.title
            p["latest_action"] = r.latest_action
    return parsed
