from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.bill import Bill
from app.models.committee import Committee, CommitteeMembership
from app.models.crosswalk import IdCrosswalk
from app.models.finance import MemberFinance
from app.models.member import Member
from app.models.vote import Vote, VotePosition
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

    # Bills this member sponsored, most-recent first. The full sponsored set is
    # loaded by the per-member sponsored-legislation pipeline (so the count is
    # complete for the current Congress); we show the 20 most recent + the true
    # total.
    sponsored = (
        await db.execute(
            select(
                Bill.bill_id, Bill.bill_type, Bill.number, Bill.title,
                Bill.introduced_date, Bill.latest_action,
            )
            .where(Bill.sponsor_bioguide_id == bioguide_id)
            .order_by(nullslast(Bill.introduced_date.desc()))
            .limit(20)
        )
    ).all()

    sponsored_total = (
        await db.execute(
            select(func.count())
            .select_from(Bill)
            .where(Bill.sponsor_bioguide_id == bioguide_id)
        )
    ).scalar_one()

    # Campaign-finance totals (Increment 4). Latest cycle shown; stays null until
    # the FEC pipeline has run (needs FEC_API_KEY).
    finance_row = (
        await db.execute(
            select(MemberFinance)
            .where(MemberFinance.bioguide_id == bioguide_id)
            .order_by(MemberFinance.cycle.desc())
        )
    ).scalars().first()

    # Recent votes this member cast (most-recent first). Only loaded votes
    # appear — coverage grows as the vote pipelines walk the session.
    voting = (
        await db.execute(
            select(
                Vote.vote_id, Vote.chamber, Vote.date, Vote.question,
                Vote.result, Vote.bill_id, VotePosition.position,
            )
            .join(VotePosition, VotePosition.vote_id == Vote.vote_id)
            .where(VotePosition.bioguide_id == bioguide_id)
            .order_by(nullslast(Vote.date.desc()), Vote.roll_number.desc())
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
        "served_since": member.served_since.isoformat() if member.served_since else None,
        "photo_url": member.photo_url,
        "birthday": member.birthday.isoformat() if member.birthday else None,
        "gender": member.gender,
        "contact": member.contact,
        "leadership_role": member.leadership_role,
        "finance": {
            "cycle": finance_row.cycle,
            "fec_candidate_id": finance_row.fec_candidate_id,
            "receipts": finance_row.receipts,
            "disbursements": finance_row.disbursements,
            "cash_on_hand": finance_row.cash_on_hand,
            "debts": finance_row.debts,
            "individual_contributions": finance_row.individual_contributions,
            "pac_contributions": finance_row.pac_contributions,
            "party_contributions": finance_row.party_contributions,
            "coverage_start": finance_row.coverage_start.isoformat() if finance_row.coverage_start else None,
            "coverage_end": finance_row.coverage_end.isoformat() if finance_row.coverage_end else None,
        }
        if finance_row
        else None,
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
        "sponsored_bills_total": sponsored_total,
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
        "voting_record": [
            {
                "vote_id": v.vote_id,
                "chamber": v.chamber,
                "date": v.date.isoformat() if v.date else None,
                "question": v.question,
                "result": v.result,
                "bill_id": v.bill_id,
                "position": v.position,
            }
            for v in voting
        ],
    }
