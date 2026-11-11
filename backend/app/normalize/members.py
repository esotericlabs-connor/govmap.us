"""Layer 2 normalizer: staging JSON -> Postgres `members` and `member_terms`.

Reads the raw staging output written by app.pipelines.congress_legislators,
applies the Bioguide ID / ISO 8601 rules from AGENTS.md, and upserts into
Postgres keyed on bioguide_id. The staged file is the current roster: members
in it are in office, and members recorded as in office but missing from it are
marked departed (guarded by plan_departures). Every term of a present member is
upserted into member_terms.

Run directly: `python -m app.normalize.members` (from backend/, after the
congress_legislators pipeline has staged data and DATABASE_URL is set).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_factory
from app.models.member import Member, MemberTerm
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

# More departures than this in one load is withheld until an operator confirms
# it (refresh members --allow-roster-turnover). A handful of resignations or
# deaths between refreshes is normal; dozens means a new Congress was seated,
# or the upstream file is truncated or wrong.
MAX_UNCONFIRMED_DEPARTURES = 3

# Rows per member_terms INSERT, kept well under asyncpg's 32,767 bind-parameter
# limit (8 columns per row).
_TERM_CHUNK = 1000


@dataclass(frozen=True)
class RosterLoad:
    count: int
    departed: tuple[str, ...]
    # False when departures were found but withheld (see `withheld`).
    applied: bool
    withheld: str | None = None


def plan_departures(
    present: set[str],
    sitting: set[str],
    *,
    roster_complete: bool,
    allow_turnover: bool,
    cap: int = MAX_UNCONFIRMED_DEPARTURES,
) -> tuple[list[str], str | None]:
    """Members recorded as in office but absent from the current file have left.
    Returns (departed ids, reason the change is withheld or None)."""
    departed = sorted(sitting - present)
    if not departed:
        return departed, None
    shown = ", ".join(departed[:12]) + (f" (+{len(departed) - 12} more)" if len(departed) > 12 else "")
    if not roster_complete:
        return departed, (
            f"{len(departed)} member(s) missing from the roster ({shown}) were NOT marked "
            "departed, because some legislator records failed validation or the pull's "
            "completeness is unknown"
        )
    if len(departed) > cap and not allow_turnover:
        return departed, (
            f"{len(departed)} member(s) missing from the roster ({shown}) were NOT marked "
            f"departed: more than {cap} needs confirmation "
            "(python -m app.pipelines.refresh members --allow-roster-turnover)"
        )
    return departed, None


def to_term_rows(legislator: LegislatorRaw, source_run_id: int | None) -> list[dict]:
    """One row per term, de-duplicated on the member_terms unique key (a repeated
    key in one INSERT ... ON CONFLICT statement is an error)."""
    rows: dict[tuple[str, date], dict] = {}
    for term in legislator.terms:
        chamber = CHAMBER_MAP[term.type]
        rows[(chamber, term.start)] = {
            "bioguide_id": legislator.id.bioguide,
            "chamber": chamber,
            "state": term.state,
            "district": term.district,
            "party": term.party,
            "start_date": term.start,
            "end_date": term.end,
            "source_run_id": source_run_id,
        }
    return list(rows.values())


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


def resolve_party(legislator: LegislatorRaw, term: LegislatorTerm) -> str:
    """Party label for the member, backfilled from history when the current term
    is missing one. congress-legislators leaves `party` null on a freshly added
    current-Congress term until its contact scripts fill it in; an incumbent's
    party carries forward, so fall back to the most recent term that has one.
    Member.party is NOT NULL, so always return a string ("Unknown" as a last
    resort for the rare brand-new member with no partied term yet)."""
    if term.party:
        return term.party
    for prev in reversed(legislator.terms):
        if prev.party:
            return prev.party
    return "Unknown"


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
        "party": resolve_party(legislator, term),
        "term_start": term.start,
        "served_since": served_since(legislator),
        "fec_candidate_ids": legislator.id.fec,
        "photo_url": f"{PHOTO_URL_BASE}/{legislator.id.bioguide}.jpg",
        "birthday": legislator.bio.birthday if legislator.bio else None,
        "gender": legislator.bio.gender if legislator.bio else None,
        "contact": _contact(term),
    }


async def normalize_and_load(
    *,
    roster_complete: bool = False,
    allow_turnover: bool = False,
    source_run_id: int | None = None,
) -> RosterLoad:
    """Upsert every staged legislator as in office, mark members missing from
    the file as departed (within the guard in plan_departures), and upsert each
    present member's terms. One transaction: a failure leaves the roster as it
    was. `roster_complete` must be True (the pull skipped no legislator
    records) for any departure to be applied."""
    if not STAGING_PATH.exists():
        raise FileNotFoundError(
            f"no staging data at {STAGING_PATH} — run the congress_legislators pipeline first"
        )

    raw_records = json.loads(STAGING_PATH.read_text())
    legislators = [LegislatorRaw.model_validate(r) for r in raw_records]
    rows = [to_member_row(legislator) | {"in_office": True} for legislator in legislators]
    present = {row["bioguide_id"] for row in rows}
    if len(present) != len(rows):
        raise ValueError("legislators staging file lists a bioguide id more than once")
    terms = [t for legislator in legislators for t in to_term_rows(legislator, source_run_id)]

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
            "in_office": stmt.excluded.in_office,
            "updated_at": func.now(),
        }
        stmt = stmt.on_conflict_do_update(index_elements=[Member.bioguide_id], set_=update_cols)
        await session.execute(stmt)

        sitting = set(
            (
                await session.execute(
                    select(Member.bioguide_id).where(Member.in_office.is_(True))
                )
            ).scalars()
        )
        departed, withheld = plan_departures(
            present,
            sitting,
            roster_complete=roster_complete,
            allow_turnover=allow_turnover,
        )
        if departed and withheld is None:
            await session.execute(
                update(Member)
                .where(Member.bioguide_id.in_(departed))
                .values(in_office=False, updated_at=func.now())
            )

        for start in range(0, len(terms), _TERM_CHUNK):
            chunk = terms[start : start + _TERM_CHUNK]
            term_stmt = pg_insert(MemberTerm).values(chunk)
            term_stmt = term_stmt.on_conflict_do_update(
                constraint="uq_member_terms_member_chamber_start",
                set_={
                    "state": term_stmt.excluded.state,
                    "district": term_stmt.excluded.district,
                    "party": term_stmt.excluded.party,
                    "end_date": term_stmt.excluded.end_date,
                    "source_run_id": term_stmt.excluded.source_run_id,
                },
            )
            await session.execute(term_stmt)
        await session.commit()

    if withheld:
        logger.warning("roster: %s", withheld)
    elif departed:
        logger.info("roster: marked %d member(s) departed: %s", len(departed), ", ".join(departed))
    logger.info("normalized and upserted %d members, %d terms", len(rows), len(terms))
    return RosterLoad(
        count=len(rows),
        departed=tuple(departed),
        applied=withheld is None,
        withheld=withheld,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Run on its own, this load can't know whether the pull skipped records,
    # so departures are reported but not applied.
    asyncio.run(normalize_and_load())
