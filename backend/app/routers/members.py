from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.bill import Bill
from app.models.committee import Committee, CommitteeMembership
from app.models.crosswalk import IdCrosswalk
from app.models.member import Member
from app.schemas.member import MemberOut

router = APIRouter(prefix="/api/members", tags=["members"])


@router.get("", response_model=list[MemberOut])
async def list_members(
    db: AsyncSession = Depends(get_db),
    chamber: Literal["house", "senate"] | None = None,
    state: str | None = Query(default=None, min_length=2, max_length=2),
    party: str | None = None,
    # Cap comfortably above the ~535 voting members + non-voting delegates so
    # the full roster is returnable in one request without silently dropping
    # records (the House delegates + PR resident commissioner push the real
    # count past 535).
    limit: int = Query(default=100, le=600),
    offset: int = 0,
) -> list[Member]:
    stmt = select(Member).order_by(Member.state, Member.last_name)
    if chamber:
        stmt = stmt.where(Member.chamber == chamber)
    if state:
        stmt = stmt.where(Member.state == state.upper())
    if party:
        stmt = stmt.where(Member.party == party)
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{bioguide_id}")
async def member_detail(bioguide_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Full member profile: core fields + cross-source IDs + committee seats.
    The backing endpoint for the member detail page (Increment 5); bills/votes/
    finance/disclosures get folded in as those tables land."""
    member = (
        await db.execute(select(Member).where(Member.bioguide_id == bioguide_id))
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="member not found")

    ids = (
        await db.execute(select(IdCrosswalk).where(IdCrosswalk.bioguide_id == bioguide_id))
    ).scalar_one_or_none()

    committees = (
        await db.execute(
            select(
                Committee.committee_id,
                Committee.name,
                Committee.parent_committee_id,
                CommitteeMembership.role,
                CommitteeMembership.side,
            )
            .join(CommitteeMembership, CommitteeMembership.committee_id == Committee.committee_id)
            .where(CommitteeMembership.bioguide_id == bioguide_id)
            .order_by(Committee.name)
        )
    ).all()

    # Recent bills this member sponsored (most-recently-updated first). Only the
    # bills currently loaded appear — coverage grows as the bills pipeline walks
    # the corpus.
    sponsored = (
        await db.execute(
            select(
                Bill.bill_id, Bill.bill_type, Bill.number, Bill.title,
                Bill.introduced_date, Bill.latest_action,
            )
            .where(Bill.sponsor_bioguide_id == bioguide_id)
            .order_by(nullslast(Bill.update_date.desc()))
            .limit(20)
        )
    ).all()

    return {
        "bioguide_id": member.bioguide_id,
        "first_name": member.first_name,
        "last_name": member.last_name,
        "official_full_name": member.official_full_name,
        "chamber": member.chamber,
        "state": member.state,
        "district": member.district,
        "party": member.party,
        "term_start": member.term_start.isoformat() if member.term_start else None,
        "photo_url": member.photo_url,
        "birthday": member.birthday.isoformat() if member.birthday else None,
        "gender": member.gender,
        "contact": member.contact,
        "leadership_role": member.leadership_role,
        "ids": {
            "fec": ids.fec_ids if ids else [],
            "govtrack": ids.govtrack if ids else None,
            "opensecrets": ids.opensecrets if ids else None,
            "thomas": ids.thomas if ids else None,
            "lis": ids.lis if ids else None,
        },
        "committees": [
            {
                "committee_id": c.committee_id,
                "name": c.name,
                "parent_committee_id": c.parent_committee_id,
                "role": c.role,
                "side": c.side,
            }
            for c in committees
        ],
        "sponsored_bills": [
            {
                "bill_id": b.bill_id,
                "bill_type": b.bill_type,
                "number": b.number,
                "title": b.title,
                "introduced_date": b.introduced_date.isoformat() if b.introduced_date else None,
                "latest_action": b.latest_action,
            }
            for b in sponsored
        ],
    }
