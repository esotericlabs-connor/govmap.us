"""Layer 2 normalizer: committees + membership staging -> Postgres.

Flattens committees-current.yaml (parents + nested subcommittees) into the
committees table, and committee-membership-current.yaml into
committee_memberships. Subcommittee committee_id = parent thomas_id + the
subcommittee's 2-digit thomas_id (matches the membership file's keys).

Must run after the members + committees exist (FKs). Memberships are replaced
wholesale each run — they churn with reorganizations, and a full swap inside one
transaction avoids drift.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_factory
from app.models.committee import Committee, CommitteeMembership
from app.schemas.committee import CommitteeMemberRaw, CommitteeRaw

logger = logging.getLogger(__name__)

STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
COMMITTEES_PATH = STAGING_DIR / "committees_raw.json"
MEMBERSHIP_PATH = STAGING_DIR / "committee_membership_raw.json"

_COMMITTEE_COLS = ("thomas_id", "name", "chamber", "committee_type", "parent_committee_id", "url")


def committee_rows(committees: list[CommitteeRaw]) -> list[dict]:
    """Parents first, then all subcommittees, so the self-referential parent FK
    is always satisfiable during the bulk insert."""
    parents: list[dict] = []
    subs: list[dict] = []
    for c in committees:
        parents.append(
            {
                "committee_id": c.thomas_id,
                "thomas_id": c.thomas_id,
                "name": c.name,
                "chamber": c.type,
                "committee_type": None,
                "parent_committee_id": None,
                "url": c.url,
            }
        )
        for sub in c.subcommittees:
            subs.append(
                {
                    "committee_id": c.thomas_id + sub.thomas_id,
                    "thomas_id": sub.thomas_id,
                    "name": sub.name,
                    "chamber": c.type,
                    "committee_type": None,
                    "parent_committee_id": c.thomas_id,
                    "url": None,
                }
            )
    return parents + subs


def membership_rows(membership: dict[str, list[dict]], known_committee_ids: set[str]) -> list[dict]:
    rows: list[dict] = []
    for code, members in membership.items():
        if code not in known_committee_ids:
            continue  # membership for a committee not in committees-current
        for m in members:
            entry = CommitteeMemberRaw.model_validate(m)
            if not entry.bioguide:
                continue  # can't join without a Bioguide ID
            rows.append(
                {
                    "committee_id": code,
                    "bioguide_id": entry.bioguide,
                    "role": entry.title,
                    "rank": entry.rank,
                    "side": entry.party,  # "majority" | "minority"
                }
            )
    return rows


async def load_committees() -> int:
    for path in (COMMITTEES_PATH, MEMBERSHIP_PATH):
        if not path.exists():
            raise FileNotFoundError(f"no staging data at {path} — run the pipeline first")

    committees = [CommitteeRaw.model_validate(c) for c in json.loads(COMMITTEES_PATH.read_text())]
    crows = committee_rows(committees)
    known = {r["committee_id"] for r in crows}
    mrows = membership_rows(json.loads(MEMBERSHIP_PATH.read_text()), known)

    async with async_session_factory() as session:
        cstmt = pg_insert(Committee).values(crows)
        cupdate = {c: getattr(cstmt.excluded, c) for c in _COMMITTEE_COLS}
        cstmt = cstmt.on_conflict_do_update(index_elements=[Committee.committee_id], set_=cupdate)
        await session.execute(cstmt)

        # Full replace of memberships (they change with reorganizations).
        await session.execute(delete(CommitteeMembership))
        if mrows:
            await session.execute(pg_insert(CommitteeMembership).values(mrows))
        await session.commit()

    logger.info("loaded %d committees, %d memberships", len(crows), len(mrows))
    return len(crows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(load_committees())
