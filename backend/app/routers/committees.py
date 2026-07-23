from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.committee import Committee, CommitteeMembership
from app.models.member import Member
from app.schemas.committee import CommitteeOut

router = APIRouter(prefix="/api/committees", tags=["committees"])


@router.get("", response_model=list[CommitteeOut])
async def list_committees(
    db: AsyncSession = Depends(get_db),
    chamber: Literal["house", "senate", "joint"] | None = None,
) -> list[Committee]:
    stmt = select(Committee).order_by(Committee.chamber, Committee.name)
    if chamber:
        stmt = stmt.where(Committee.chamber == chamber)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{committee_id}")
async def committee_detail(committee_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    committee = (
        await db.execute(select(Committee).where(Committee.committee_id == committee_id))
    ).scalar_one_or_none()
    if committee is None:
        raise HTTPException(status_code=404, detail="committee not found")

    rows = (
        await db.execute(
            select(
                Member.bioguide_id,
                Member.official_full_name,
                Member.party,
                Member.state,
                Member.photo_url,
                CommitteeMembership.role,
                CommitteeMembership.side,
                CommitteeMembership.rank,
            )
            .join(CommitteeMembership, CommitteeMembership.bioguide_id == Member.bioguide_id)
            .where(CommitteeMembership.committee_id == committee_id)
            .order_by(CommitteeMembership.side, CommitteeMembership.rank)
        )
    ).all()

    return {
        "committee_id": committee.committee_id,
        "name": committee.name,
        "chamber": committee.chamber,
        "committee_type": committee.committee_type,
        "parent_committee_id": committee.parent_committee_id,
        "url": committee.url,
        "members": [
            {
                "bioguide_id": r.bioguide_id,
                "official_full_name": r.official_full_name,
                "party": r.party,
                "state": r.state,
                "photo_url": r.photo_url,
                "role": r.role,
                "side": r.side,
                "rank": r.rank,
            }
            for r in rows
        ],
    }
