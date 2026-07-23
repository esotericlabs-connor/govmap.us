"""Congress-dashboard + map endpoints.

Three read-only endpoints backing the `/congress` entry page:
  - GET /api/map      compact party/link index for the interactive US map
  - GET /api/summary  per-chamber party balance (the House/Senate split bars)
  - GET /api/lookup   ZIP → your senators + representative(s)

/map and /summary are derived entirely from the already-loaded `members` table
(no new data dependency). /lookup additionally joins `zip_districts`, populated
by the zip_crosswalk pipeline. All responses are public office-holder data.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.member import Member
from app.models.zip_district import ZipDistrict

router = APIRouter(prefix="/api", tags=["congress"])


def _party_bucket(party: str | None) -> str:
    """Collapse the free-text party label to D / R / I for the balance bars.
    Anything that isn't clearly Democrat or Republican buckets as Independent."""
    p = (party or "").strip().lower()
    if p.startswith("d"):
        return "D"
    if p.startswith("r"):
        return "R"
    return "I"


def _member_summary(m: Member) -> dict:
    """Compact member shape shared by /lookup (and mirrored on the frontend)."""
    return {
        "bioguide_id": m.bioguide_id,
        "official_full_name": m.official_full_name,
        "last_name": m.last_name,
        "party": m.party,
        "state": m.state,
        "district": m.district,
        "chamber": m.chamber,
        "photo_url": m.photo_url,
    }


@router.get("/map")
async def congress_map(db: AsyncSession = Depends(get_db)) -> dict:
    """Party/link index for the map, keyed to geometry the frontend renders.

    House is keyed `STATE-DISTRICT` (e.g. `WA-7`; district 0 = at-large /
    single-district state or non-voting delegate). Senate is keyed by state
    (its two seats). Small enough to ship on every page load."""
    rows = (
        await db.execute(
            select(
                Member.bioguide_id,
                Member.last_name,
                Member.party,
                Member.state,
                Member.district,
                Member.chamber,
            )
        )
    ).all()

    house: dict[str, dict] = {}
    senate: dict[str, list[dict]] = {}
    for r in rows:
        entry = {"bioguide": r.bioguide_id, "last_name": r.last_name, "party": r.party}
        if r.chamber == "house":
            district = r.district if r.district is not None else 0
            house[f"{r.state}-{district}"] = entry
        elif r.chamber == "senate":
            senate.setdefault(r.state, []).append(entry)

    return {"house": house, "senate": senate}


@router.get("/summary")
async def chamber_summary(db: AsyncSession = Depends(get_db)) -> dict:
    """Per-chamber party balance: {house:{D,R,I,total}, senate:{D,R,I,total}}."""
    rows = (await db.execute(select(Member.chamber, Member.party))).all()

    out = {
        "house": {"D": 0, "R": 0, "I": 0, "total": 0},
        "senate": {"D": 0, "R": 0, "I": 0, "total": 0},
    }
    for chamber, party in rows:
        if chamber not in out:
            continue
        out[chamber][_party_bucket(party)] += 1
        out[chamber]["total"] += 1
    return out


@router.get("/lookup")
async def lookup(
    zip_code: str = Query(..., alias="zip", pattern=r"^\d{5}$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """ZIP → the two senators for the state(s) it touches + the House
    representative(s) for the district(s) it touches. A ZIP that straddles a
    district boundary returns every matching representative."""
    pairs = (
        await db.execute(
            select(ZipDistrict.state, ZipDistrict.district).where(
                ZipDistrict.zip == zip_code
            )
        )
    ).all()

    districts = [{"state": s, "district": d} for s, d in pairs]
    states = sorted({s for s, _ in pairs})

    senators: list[dict] = []
    representatives: list[dict] = []

    if states:
        sen = (
            await db.execute(
                select(Member)
                .where(Member.chamber == "senate", Member.state.in_(states))
                .order_by(Member.state, Member.last_name)
            )
        ).scalars().all()
        senators = [_member_summary(m) for m in sen]

        conds = [
            and_(Member.state == p["state"], Member.district == p["district"])
            for p in districts
        ]
        if conds:
            reps = (
                await db.execute(
                    select(Member)
                    .where(Member.chamber == "house", or_(*conds))
                    .order_by(Member.state, Member.district)
                )
            ).scalars().all()
            representatives = [_member_summary(m) for m in reps]

    return {
        "zip": zip_code,
        "districts": districts,
        "senators": senators,
        "representatives": representatives,
    }
