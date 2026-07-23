"""Layer 2 normalizer: House + Senate vote staging -> votes / vote_positions.

Reads both staged files (house_votes_raw.json, senate_votes_raw.json). House
positions carry Bioguide IDs directly; **Senate positions carry LIS member ids
and are resolved to Bioguide via id_crosswalk.lis** — the crosswalk backbone's
first real cross-source join. Senate positions with no crosswalk hit (e.g. a
former senator not in the current map) are skipped and counted.

Votes upsert on vote_id; each refreshed vote's positions are fully replaced.
Inserts are chunked under Postgres' 32767 bind-parameter cap (100 House votes ×
~435 members is ~43k rows).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_factory
from app.models.crosswalk import IdCrosswalk
from app.models.vote import Vote, VotePosition

logger = logging.getLogger(__name__)

STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
HOUSE_PATH = STAGING_DIR / "house_votes_raw.json"
SENATE_PATH = STAGING_DIR / "senate_votes_raw.json"

_CHUNK = 1000

_VOTE_UPDATE_COLS = (
    "chamber", "congress", "session", "roll_number", "date",
    "question", "result", "bill_id", "totals", "source_url",
)


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text()) if path.exists() else []


def _vote_row(v: dict) -> dict:
    return {
        "vote_id": v["vote_id"],
        "chamber": v["chamber"],
        "congress": v["congress"],
        "session": v["session"],
        "roll_number": v["roll_number"],
        "date": date.fromisoformat(v["date"]) if v.get("date") else None,
        "question": v.get("question"),
        "result": v.get("result"),
        "bill_id": v.get("bill_id"),
        "totals": v.get("totals"),
        "source_url": v.get("source_url"),
    }


async def _insert_chunked(session, model, rows: list[dict]) -> None:
    for i in range(0, len(rows), _CHUNK):
        await session.execute(pg_insert(model).values(rows[i : i + _CHUNK]))


async def normalize_and_load() -> int:
    house = _load(HOUSE_PATH)
    senate = _load(SENATE_PATH)
    if not house and not senate:
        logger.info("votes normalizer: nothing staged")
        return 0

    async with async_session_factory() as session:
        # LIS -> Bioguide map for resolving Senate positions.
        cw = (
            await session.execute(
                select(IdCrosswalk.lis, IdCrosswalk.bioguide_id).where(IdCrosswalk.lis.isnot(None))
            )
        ).all()
        lis_to_bioguide = {row.lis: row.bioguide_id for row in cw}

        vote_rows: list[dict] = []
        vote_ids: list[str] = []
        pos_rows: list[dict] = []
        senate_unresolved = 0

        for v in house:
            vote_rows.append(_vote_row(v))
            vote_ids.append(v["vote_id"])
            seen: set[str] = set()
            for p in v.get("positions", []):
                bio = p.get("bioguide_id")
                if not bio or bio in seen:
                    continue
                seen.add(bio)
                pos_rows.append({"vote_id": v["vote_id"], "bioguide_id": bio, "position": p.get("position")})

        for v in senate:
            vote_rows.append(_vote_row(v))
            vote_ids.append(v["vote_id"])
            seen = set()
            for p in v.get("positions", []):
                bio = lis_to_bioguide.get(p.get("lis_member_id"))
                if not bio:
                    senate_unresolved += 1
                    continue
                if bio in seen:
                    continue
                seen.add(bio)
                pos_rows.append({"vote_id": v["vote_id"], "bioguide_id": bio, "position": p.get("position")})

        # Upsert votes (chunked).
        for i in range(0, len(vote_rows), 500):
            chunk = vote_rows[i : i + 500]
            stmt = pg_insert(Vote).values(chunk)
            update = {c: getattr(stmt.excluded, c) for c in _VOTE_UPDATE_COLS}
            update["updated_at"] = func.now()
            stmt = stmt.on_conflict_do_update(index_elements=[Vote.vote_id], set_=update)
            await session.execute(stmt)

        # Full-replace positions for just the refreshed votes.
        for i in range(0, len(vote_ids), 500):
            await session.execute(
                delete(VotePosition).where(VotePosition.vote_id.in_(vote_ids[i : i + 500]))
            )
        await _insert_chunked(session, VotePosition, pos_rows)

        await session.commit()

    logger.info(
        "normalized %d votes, %d positions (%d senate positions unresolved via crosswalk)",
        len(vote_rows), len(pos_rows), senate_unresolved,
    )
    return len(vote_rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(normalize_and_load())
