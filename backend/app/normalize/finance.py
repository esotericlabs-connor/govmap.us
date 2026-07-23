"""Layer 2 normalizer: FEC finance staging -> Postgres member_finance.

Upserts on (bioguide_id, cycle) so a partial pull (a few candidates rate-limited)
never wipes good prior data. Amounts are stored as-is (USD floats from OpenFEC).

Run directly: `python -m app.normalize.finance`.
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
from app.models.finance import MemberFinance

logger = logging.getLogger(__name__)

STAGING_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "staging" / "member_finance_raw.json"
)

_CHUNK = 2000

_UPDATE_COLS = (
    "fec_candidate_id",
    "receipts",
    "disbursements",
    "cash_on_hand",
    "debts",
    "individual_contributions",
    "pac_contributions",
    "party_contributions",
    "coverage_start",
    "coverage_end",
)


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _row(r: dict) -> dict:
    row = dict(r)
    row["coverage_start"] = _d(r.get("coverage_start"))
    row["coverage_end"] = _d(r.get("coverage_end"))
    return row


async def load_finance() -> int:
    if not STAGING_PATH.exists():
        raise FileNotFoundError(
            f"no staging data at {STAGING_PATH} — run the fec_finance pipeline first"
        )

    staged = json.loads(STAGING_PATH.read_text())
    # Dedupe by (bioguide, cycle) — the PK.
    rows_by_key: dict[tuple[str, int], dict] = {}
    for r in staged:
        rows_by_key[(r["bioguide_id"], r["cycle"])] = _row(r)
    rows = list(rows_by_key.values())
    if not rows:
        logger.info("finance: nothing to load")
        return 0

    async with async_session_factory() as session:
        for i in range(0, len(rows), _CHUNK):
            chunk = rows[i : i + _CHUNK]
            stmt = pg_insert(MemberFinance).values(chunk)
            update = {c: getattr(stmt.excluded, c) for c in _UPDATE_COLS}
            update["updated_at"] = func.now()
            stmt = stmt.on_conflict_do_update(
                index_elements=[MemberFinance.bioguide_id, MemberFinance.cycle],
                set_=update,
            )
            await session.execute(stmt)
        await session.commit()

    logger.info("finance: upserted %d member-cycle finance rows", len(rows))
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(load_finance())
