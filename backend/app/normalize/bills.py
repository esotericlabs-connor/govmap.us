"""Layer 2 normalizer: bills staging -> Postgres bills / bill_actions / cosponsors.

Reads the bundle staged by app.pipelines.congress_gov_bills and upserts. Like
the members normalizer, it re-validates the staged JSON through the Pydantic
`*Raw` schemas so ISO date strings deserialize back into `datetime.date` objects
(asyncpg rejects bare strings for Date columns).

Bills upsert on bill_id; each refreshed bill's actions and cosponsors are fully
replaced (they're re-fetched whole, and cosponsors can be withdrawn), scoped to
just the bills in this batch so untouched bills are left alone. Inserts are
chunked — 250 bills' worth of actions/cosponsors exceeds Postgres' 32767
bind-parameter limit for a single INSERT.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from datetime import date
from pathlib import Path

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_factory
from app.models.bill import Bill, BillAction, Cosponsor
from app.schemas.bill import (
    BillActionRaw,
    BillDetailRaw,
    BillSummaryRaw,
    BillTextVersionRaw,
    CosponsorRaw,
)

logger = logging.getLogger(__name__)

STAGING_PATH = Path(__file__).resolve().parents[2] / "data" / "staging" / "bills_raw.json"

# Row count per INSERT — keeps params under Postgres' 32767 cap for every table
# here (bills has the widest row at ~13 cols: 1000 * 13 = 13000).
_CHUNK = 1000

_BILL_UPDATE_COLS = (
    "congress", "bill_type", "number", "title", "sponsor_bioguide_id",
    "introduced_date", "latest_action", "latest_action_date", "status",
    "policy_area", "update_date", "summary", "summary_date", "text_url",
    "text_version",
)


def _strip_html(raw: str | None) -> str | None:
    """CRS summaries come as HTML; reduce to readable plain text so the frontend
    never needs dangerouslySetInnerHTML. Lists → bullets, blocks → newlines."""
    if not raw:
        return None
    t = re.sub(r"(?i)<li[^>]*>", "\n• ", raw)
    t = re.sub(r"(?i)</(p|div|li|ul|ol|h[1-6])>", "\n", t)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", t)
    return t.strip() or None


def _latest_summary(summaries: list[BillSummaryRaw]) -> tuple[str | None, date | None]:
    if not summaries:
        return None, None
    latest = max(summaries, key=lambda s: s.actionDate or s.updateDate or date.min)
    return _strip_html(latest.text), latest.actionDate


def _latest_text(versions: list[BillTextVersionRaw]) -> tuple[str | None, str | None]:
    """URL + label of the most recent full-text version (prefer readable HTML,
    then PDF, then whatever's present)."""
    if not versions:
        return None, None
    latest = max(versions, key=lambda v: v.date or date.min)
    fmt = None
    for pref in ("Formatted Text", "PDF"):
        fmt = next((f for f in latest.formats if f.type == pref and f.url), None)
        if fmt:
            break
    if fmt is None:
        fmt = next((f for f in latest.formats if f.url), None)
    return (fmt.url if fmt else None), latest.type


def to_bill_row(bill: BillDetailRaw) -> dict:
    btype = bill.type.lower()
    sponsor = bill.sponsors[0].bioguideId if bill.sponsors else None
    latest = bill.latestAction
    return {
        "bill_id": f"{btype}{bill.number}-{bill.congress}",
        "congress": bill.congress,
        "bill_type": btype,
        "number": bill.number,
        "title": bill.title,
        "sponsor_bioguide_id": sponsor,
        "introduced_date": bill.introducedDate,
        "latest_action": latest.text if latest else None,
        "latest_action_date": latest.actionDate if latest else None,
        # Only the unambiguous, source-derived status; no invented taxonomy.
        "status": "Became Law" if bill.laws else None,
        "policy_area": bill.policyArea.name if bill.policyArea else None,
        "update_date": bill.updateDate,
    }


def _action_chamber(source_name: str | None) -> str | None:
    """Normalize Congress.gov's sourceSystem.name (e.g. 'House committee actions',
    'House floor actions', 'Senate', 'Library of Congress') to a clean chamber.
    The floor-vs-committee distinction is preserved in action_type, so chamber
    stays a plain House/Senate; Library-of-Congress-coded actions have no
    chamber. (The raw name also overflows the String(20) column — 'House
    committee actions' is 23 chars.)"""
    if not source_name:
        return None
    if source_name.startswith("House"):
        return "House"
    if source_name.startswith("Senate"):
        return "Senate"
    return None


def action_rows(bill_id: str, actions: list[BillActionRaw]) -> list[dict]:
    return [
        {
            "bill_id": bill_id,
            "seq": seq,
            "action_date": a.actionDate,
            "chamber": _action_chamber(a.sourceSystem.name if a.sourceSystem else None),
            "text": a.text,
            "action_type": a.type,
        }
        for seq, a in enumerate(actions)
    ]


def cosponsor_rows(bill_id: str, cosponsors: list[CosponsorRaw]) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()  # (bill_id, bioguide_id) is the PK — dedupe defensively
    for c in cosponsors:
        if not c.bioguideId or c.bioguideId in seen:
            continue
        seen.add(c.bioguideId)
        rows.append(
            {
                "bill_id": bill_id,
                "bioguide_id": c.bioguideId,
                "sponsorship_date": c.sponsorshipDate,
                "is_original": c.isOriginalCosponsor,
            }
        )
    return rows


async def _insert_chunked(session, model, rows: list[dict]) -> None:
    for i in range(0, len(rows), _CHUNK):
        await session.execute(pg_insert(model).values(rows[i : i + _CHUNK]))


async def normalize_and_load() -> int:
    if not STAGING_PATH.exists():
        raise FileNotFoundError(
            f"no staging data at {STAGING_PATH} — run the congress_gov_bills pipeline first"
        )

    staged = json.loads(STAGING_PATH.read_text())
    bill_rows: list[dict] = []
    bill_ids: list[str] = []
    all_actions: list[dict] = []
    all_cosponsors: list[dict] = []
    for entry in staged:
        bill = BillDetailRaw.model_validate(entry["bill"])
        row = to_bill_row(bill)
        summaries = [BillSummaryRaw.model_validate(s) for s in entry.get("summaries", [])]
        text_versions = [
            BillTextVersionRaw.model_validate(t) for t in entry.get("text_versions", [])
        ]
        row["summary"], row["summary_date"] = _latest_summary(summaries)
        row["text_url"], row["text_version"] = _latest_text(text_versions)
        bid = row["bill_id"]
        bill_rows.append(row)
        bill_ids.append(bid)
        actions = [BillActionRaw.model_validate(a) for a in entry.get("actions", [])]
        cosponsors = [CosponsorRaw.model_validate(c) for c in entry.get("cosponsors", [])]
        all_actions.extend(action_rows(bid, actions))
        all_cosponsors.extend(cosponsor_rows(bid, cosponsors))

    async with async_session_factory() as session:
        # Upsert bills (chunked — cap could be raised well past a single stmt).
        for i in range(0, len(bill_rows), _CHUNK):
            chunk = bill_rows[i : i + _CHUNK]
            stmt = pg_insert(Bill).values(chunk)
            update = {c: getattr(stmt.excluded, c) for c in _BILL_UPDATE_COLS}
            update["updated_at"] = func.now()
            stmt = stmt.on_conflict_do_update(index_elements=[Bill.bill_id], set_=update)
            await session.execute(stmt)

        # Full-replace actions + cosponsors for just the refreshed bills.
        await session.execute(delete(BillAction).where(BillAction.bill_id.in_(bill_ids)))
        await _insert_chunked(session, BillAction, all_actions)
        await session.execute(delete(Cosponsor).where(Cosponsor.bill_id.in_(bill_ids)))
        await _insert_chunked(session, Cosponsor, all_cosponsors)

        await session.commit()

    logger.info(
        "normalized %d bills, %d actions, %d cosponsors",
        len(bill_rows), len(all_actions), len(all_cosponsors),
    )
    return len(bill_rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(normalize_and_load())
