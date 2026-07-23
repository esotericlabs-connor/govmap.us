from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.member import Member
from app.models.vote import Vote, VotePosition
from app.schemas.vote import VoteOut

router = APIRouter(prefix="/api/votes", tags=["votes"])


@router.get("", response_model=list[VoteOut])
async def list_votes(
    db: AsyncSession = Depends(get_db),
    chamber: Literal["house", "senate"] | None = None,
    congress: int | None = None,
    session: int | None = None,
    bill_id: str | None = None,
    limit: int = Query(default=50, le=250),
    offset: int = 0,
) -> list[Vote]:
    # Most-recent first (newest date, then highest roll within a day).
    stmt = select(Vote).order_by(
        nullslast(Vote.date.desc()), Vote.chamber, Vote.roll_number.desc()
    )
    if chamber:
        stmt = stmt.where(Vote.chamber == chamber)
    if congress:
        stmt = stmt.where(Vote.congress == congress)
    if session:
        stmt = stmt.where(Vote.session == session)
    if bill_id:
        stmt = stmt.where(Vote.bill_id == bill_id)
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{vote_id}")
async def vote_detail(vote_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Full roll call: metadata + every member's position (names left-joined from
    `members`; a member no longer current shows a null name)."""
    vote = (
        await db.execute(select(Vote).where(Vote.vote_id == vote_id))
    ).scalar_one_or_none()
    if vote is None:
        raise HTTPException(status_code=404, detail="vote not found")

    rows = (
        await db.execute(
            select(
                VotePosition.bioguide_id,
                VotePosition.position,
                Member.official_full_name,
                Member.party,
                Member.state,
            )
            .outerjoin(Member, Member.bioguide_id == VotePosition.bioguide_id)
            .where(VotePosition.vote_id == vote_id)
            .order_by(nullslast(Member.state), nullslast(Member.last_name))
        )
    ).all()

    return {
        "vote_id": vote.vote_id,
        "chamber": vote.chamber,
        "congress": vote.congress,
        "session": vote.session,
        "roll_number": vote.roll_number,
        "date": vote.date.isoformat() if vote.date else None,
        "question": vote.question,
        "result": vote.result,
        "bill_id": vote.bill_id,
        "totals": vote.totals,
        "source_url": vote.source_url,
        "positions": [
            {
                "bioguide_id": r.bioguide_id,
                "official_full_name": r.official_full_name,
                "party": r.party,
                "state": r.state,
                "position": r.position,
            }
            for r in rows
        ],
    }
