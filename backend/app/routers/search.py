"""Universal search across the loaded government data.

One endpoint powering the platform's top search bar — the "search everything"
box. Returns a small, grouped set of the best matches per entity type so the UI
can render a categorized typeahead. Designed to grow: add a new entity type by
adding a block here and a group in the frontend.

Security/robustness: the query is a bound parameter (SQLAlchemy parameterizes
ILIKE values — no injection), LIKE wildcards in user input are escaped with an
explicit ESCAPE clause so `%`/`_` are literal, the term is length-bounded, and
every group is hard-capped so a one-character query can't return a huge result
set.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import nullslast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.bill import Bill
from app.models.committee import Committee
from app.models.crosswalk import IdCrosswalk
from app.models.member import Member
from app.models.vote import Vote
from app.services.search import LIKE_ESCAPE, escape_like, match_words, substring_pattern

router = APIRouter(prefix="/api/search", tags=["search"])

# Max hits returned per entity group. Small on purpose — this is a typeahead,
# not a results page.
PER_GROUP = 6
# Below this many (trimmed) characters we don't search — avoids matching
# everything on a single stray keystroke.
MIN_CHARS = 2


@router.get("")
async def search(
    q: str = Query(min_length=1, max_length=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    term = q.strip()
    empty = {"query": term, "members": [], "bills": [], "votes": [], "committees": []}
    if len(term) < MIN_CHARS:
        return empty

    # "hr 1234" -> matches bill_id "hr1234-119"
    bill_pat = substring_pattern("".join(term.split()))

    members = (
        await db.execute(
            select(
                Member.bioguide_id,
                Member.official_full_name,
                Member.party,
                Member.state,
                Member.chamber,
                Member.photo_url,
                Member.in_office,
            )
            .where(
                or_(
                    match_words(
                        term, Member.official_full_name, Member.first_name, Member.last_name
                    ),
                    # Case-insensitive exact state code; "%%" must not match every state.
                    Member.state.ilike(escape_like(term), escape=LIKE_ESCAPE),
                    Member.bioguide_id.ilike(escape_like(term), escape=LIKE_ESCAPE),
                    select(IdCrosswalk.bioguide_id)
                    .where(
                        IdCrosswalk.bioguide_id == Member.bioguide_id,
                        IdCrosswalk.fec_ids.any(term.upper()),
                    )
                    .exists(),
                )
            )
            # Former members stay searchable, after the current ones.
            .order_by(Member.in_office.desc(), Member.last_name)
            .limit(PER_GROUP)
        )
    ).all()

    bills = (
        await db.execute(
            select(Bill.bill_id, Bill.bill_type, Bill.number, Bill.title, Bill.latest_action)
            .where(
                or_(
                    match_words(term, Bill.title, Bill.bill_id),
                    Bill.bill_id.ilike(bill_pat, escape=LIKE_ESCAPE),
                )
            )
            .order_by(nullslast(Bill.update_date.desc()))
            .limit(PER_GROUP)
        )
    ).all()

    votes = (
        await db.execute(
            select(Vote.vote_id, Vote.chamber, Vote.date, Vote.question, Vote.result)
            .where(match_words(term, Vote.question, Vote.vote_id))
            .order_by(nullslast(Vote.date.desc()))
            .limit(PER_GROUP)
        )
    ).all()

    committees = (
        await db.execute(
            select(Committee.committee_id, Committee.name, Committee.chamber)
            .where(match_words(term, Committee.name, Committee.committee_id))
            .order_by(Committee.name)
            .limit(PER_GROUP)
        )
    ).all()

    return {
        "query": term,
        "members": [
            {
                "bioguide_id": m.bioguide_id,
                "official_full_name": m.official_full_name,
                "party": m.party,
                "state": m.state,
                "chamber": m.chamber,
                "photo_url": m.photo_url,
                "in_office": m.in_office,
            }
            for m in members
        ],
        "bills": [
            {
                "bill_id": b.bill_id,
                "bill_type": b.bill_type,
                "number": b.number,
                "title": b.title,
                "latest_action": b.latest_action,
            }
            for b in bills
        ],
        "votes": [
            {
                "vote_id": v.vote_id,
                "chamber": v.chamber,
                "date": v.date.isoformat() if v.date else None,
                "question": v.question,
                "result": v.result,
            }
            for v in votes
        ],
        "committees": [
            {"committee_id": c.committee_id, "name": c.name, "chamber": c.chamber}
            for c in committees
        ],
    }
