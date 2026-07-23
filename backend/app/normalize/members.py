"""Layer 2 normalizer: staging JSON -> Postgres `members` table.

Reads the raw staging output written by app.pipelines.congress_legislators,
applies the Bioguide ID / ISO 8601 rules from AGENTS.md, and upserts into
Postgres keyed on bioguide_id.

Run directly: `python -m app.normalize.members` (from backend/, after the
congress_legislators pipeline has staged data and DATABASE_URL is set).
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
from app.models.member import Member
from app.schemas.member import LegislatorRaw, LegislatorTerm

logger = logging.getLogger(__name__)

# backend/app/normalize/members.py -> parents[2] == backend/
STAGING_PATH = Path(__file__).resolve().parents[2] / "data" / "staging" / "legislators_raw.json"

CHAMBER_MAP = {"rep": "house", "sen": "senate"}

# unitedstates/images serves public-domain member portraits at a deterministic
# URL keyed by Bioguide ID (verified 200 image/jpeg). Because the URL is fully
# derivable, it's set here rather than via a separate pull pipeline; the
# frontend falls back to initials for the rare member without a portrait. If we
# ever need existence-verification or self-hosting, this becomes a real
# Layer-1 pipeline (see AGENTS.md).
PHOTO_URL_BASE = "https://unitedstates.github.io/images/congress/225x275"


def current_term(legislator: LegislatorRaw) -> LegislatorTerm:
    # legislators-current.yaml lists each member's terms chronologically;
    # the last entry is always their active term.
    return legislator.terms[-1]


def served_since(legislator: LegislatorRaw) -> date:
    """The real "in office since": walk back from the current term through
    *contiguous same-chamber* terms and return the earliest start. Consecutive
    congressional terms are back-to-back (a term ends and the next begins on the
    same ~Jan-3), so a multi-year gap means the member left and returned (not
    continuous), and a chamber switch (House → Senate, like Cantwell) starts a
    new tenure. Returns 2001 for Cantwell, 2003 for Rogers — not 2025."""
    terms = legislator.terms
    current = terms[-1]
    chamber = current.type
    since = current.start
    for prev in reversed(terms[:-1]):
        if prev.type != chamber:
            break
        # >~1yr between the prior term's end and the kept term's start = a gap.
        if (since - prev.end).days > 400:
            break
        since = prev.start
    return since


def _contact(term: LegislatorTerm) -> dict | None:
    fields = {"office": term.office, "phone": term.phone, "url": term.url, "address": term.address}
    fields = {k: v for k, v in fields.items() if v}
    return fields or None


def to_member_row(legislator: LegislatorRaw) -> dict:
    term = current_term(legislator)
    full_name = legislator.name.official_full or f"{legislator.name.first} {legislator.name.last}"
    return {
        "bioguide_id": legislator.id.bioguide,
        "first_name": legislator.name.first,
        "last_name": legislator.name.last,
        "official_full_name": full_name,
        "chamber": CHAMBER_MAP[term.type],
        "state": term.state,
        "district": term.district,
        "party": term.party,
        "term_start": term.start,
        "served_since": served_since(legislator),
        "fec_candidate_ids": legislator.id.fec,
        "photo_url": f"{PHOTO_URL_BASE}/{legislator.id.bioguide}.jpg",
        "birthday": legislator.bio.birthday if legislator.bio else None,
        "gender": legislator.bio.gender if legislator.bio else None,
        "contact": _contact(term),
    }


async def normalize_and_load() -> int:
    if not STAGING_PATH.exists():
        raise FileNotFoundError(
            f"no staging data at {STAGING_PATH} — run the congress_legislators pipeline first"
        )

    raw_records = json.loads(STAGING_PATH.read_text())
    rows = [to_member_row(LegislatorRaw.model_validate(r)) for r in raw_records]

    async with async_session_factory() as session:
        stmt = pg_insert(Member).values(rows)
        update_cols = {
            "first_name": stmt.excluded.first_name,
            "last_name": stmt.excluded.last_name,
            "official_full_name": stmt.excluded.official_full_name,
            "chamber": stmt.excluded.chamber,
            "state": stmt.excluded.state,
            "district": stmt.excluded.district,
            "party": stmt.excluded.party,
            "term_start": stmt.excluded.term_start,
            "served_since": stmt.excluded.served_since,
            "fec_candidate_ids": stmt.excluded.fec_candidate_ids,
            "photo_url": stmt.excluded.photo_url,
            "birthday": stmt.excluded.birthday,
            "gender": stmt.excluded.gender,
            "contact": stmt.excluded.contact,
            "updated_at": func.now(),
        }
        stmt = stmt.on_conflict_do_update(index_elements=[Member.bioguide_id], set_=update_cols)
        await session.execute(stmt)
        await session.commit()

    logger.info("normalized and upserted %d members", len(rows))
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(normalize_and_load())
