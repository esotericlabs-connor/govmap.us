"""Layer 2 normalizer: legislators staging -> id_crosswalk table.

Builds the Bioguide-keyed cross-source ID map from the `id` block of
legislators-current.yaml (already staged by the congress_legislators pipeline).
Must run after the members normalizer, since id_crosswalk.bioguide_id FKs
members.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_factory
from app.models.crosswalk import IdCrosswalk
from app.schemas.member import LegislatorRaw

logger = logging.getLogger(__name__)

STAGING_PATH = Path(__file__).resolve().parents[2] / "data" / "staging" / "legislators_raw.json"

_COLS = ("fec_ids", "govtrack", "opensecrets", "thomas", "lis", "votesmart", "wikidata")


def to_crosswalk_row(legislator: LegislatorRaw) -> dict:
    ids = legislator.id
    return {
        "bioguide_id": ids.bioguide,
        "fec_ids": ids.fec,
        "govtrack": ids.govtrack,
        "opensecrets": ids.opensecrets,
        "thomas": ids.thomas,
        "lis": ids.lis,
        "votesmart": ids.votesmart,
        "wikidata": ids.wikidata,
    }


async def load_crosswalk() -> int:
    if not STAGING_PATH.exists():
        raise FileNotFoundError(f"no staging data at {STAGING_PATH} — run the pipeline first")

    raw = json.loads(STAGING_PATH.read_text())
    rows = [to_crosswalk_row(LegislatorRaw.model_validate(r)) for r in raw]

    async with async_session_factory() as session:
        stmt = pg_insert(IdCrosswalk).values(rows)
        update = {c: getattr(stmt.excluded, c) for c in _COLS}
        stmt = stmt.on_conflict_do_update(index_elements=[IdCrosswalk.bioguide_id], set_=update)
        await session.execute(stmt)
        await session.commit()

    logger.info("loaded %d id_crosswalk rows", len(rows))
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(load_crosswalk())
