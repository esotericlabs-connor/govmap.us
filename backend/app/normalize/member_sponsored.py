"""Layer 2 normalizer: sponsored-legislation staging -> bills upsert.

Upserts each staged sponsored bill into `bills` as an "index" row: identity +
sponsor + title + latest action + policy area. It deliberately does NOT touch
`bill_actions`/`cosponsors` (those come from the enriched bills pull) and does
NOT overwrite `update_date`/`status` on conflict, so it can never downgrade a
bill the enriched pull already filled in. Idempotent; safe to run alongside the
bills normalizer.

Run directly: `python -m app.normalize.member_sponsored`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_factory
from app.models.bill import Bill

logger = logging.getLogger(__name__)

STAGING_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "staging" / "member_sponsored_raw.json"
)

_CHUNK = 1000  # 10 cols/row -> 10000 params, under the 32767 cap.

# On conflict, only refresh the index fields — never clobber update_date/status
# that the enriched bills pull owns.
_UPDATE_COLS = (
    "title",
    "sponsor_bioguide_id",
    "introduced_date",
    "latest_action",
    "latest_action_date",
    "policy_area",
)


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _bill_row(r: dict) -> dict:
    btype = str(r["type"]).lower()
    return {
        "bill_id": f"{btype}{r['number']}-{r['congress']}",
        "congress": r["congress"],
        "bill_type": btype,
        "number": r["number"],
        "title": r.get("title"),
        "sponsor_bioguide_id": r.get("sponsor_bioguide_id"),
        "introduced_date": _d(r.get("introduced_date")),
        "latest_action": r.get("latest_action"),
        "latest_action_date": _d(r.get("latest_action_date")),
        "policy_area": r.get("policy_area"),
    }


async def load_member_sponsored() -> int:
    if not STAGING_PATH.exists():
        raise FileNotFoundError(
            f"no staging data at {STAGING_PATH} — run congress_member_sponsored first"
        )

    staged = json.loads(STAGING_PATH.read_text())
    # A bill has exactly one sponsor; dedupe by bill_id defensively.
    rows_by_id: dict[str, dict] = {}
    for r in staged:
        row = _bill_row(r)
        rows_by_id[row["bill_id"]] = row
    rows = list(rows_by_id.values())
    if not rows:
        logger.info("member_sponsored: nothing to load")
        return 0

    async with async_session_factory() as session:
        for i in range(0, len(rows), _CHUNK):
            chunk = rows[i : i + _CHUNK]
            stmt = pg_insert(Bill).values(chunk)
            update = {c: getattr(stmt.excluded, c) for c in _UPDATE_COLS}
            update["updated_at"] = func.now()
            stmt = stmt.on_conflict_do_update(index_elements=[Bill.bill_id], set_=update)
            await session.execute(stmt)
        await session.commit()

    logger.info("member_sponsored: upserted %d sponsored bills", len(rows))
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(load_member_sponsored())
