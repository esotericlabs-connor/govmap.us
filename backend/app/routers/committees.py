from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.committee import Committee, CommitteeMeeting, CommitteeMembership
from app.models.member import Member
from app.schemas.committee import CommitteeOut
from app.services.committees import referred_bills

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

    subcommittees = (
        await db.execute(
            select(Committee.committee_id, Committee.name)
            .where(Committee.parent_committee_id == committee_id)
            .order_by(Committee.name)
        )
    ).all()

    meetings = (
        await db.execute(
            select(CommitteeMeeting).where(CommitteeMeeting.committee_id == committee_id)
        )
    ).scalars().all()
    now = datetime.now(UTC)
    upcoming = sorted(
        (m for m in meetings if m.meeting_datetime and m.meeting_datetime >= now),
        key=lambda m: m.meeting_datetime,
    )
    recent = sorted(
        (m for m in meetings if not (m.meeting_datetime and m.meeting_datetime >= now)),
        key=lambda m: m.meeting_datetime or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )[:12]

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
        "subcommittees": [
            {"committee_id": s.committee_id, "name": s.name} for s in subcommittees
        ],
        "upcoming_meetings": [_meeting_dict(m) for m in upcoming],
        "recent_meetings": [_meeting_dict(m) for m in recent],
    }


def _meeting_dict(m: CommitteeMeeting) -> dict:
    return {
        "event_id": m.event_id,
        "title": m.title,
        "meeting_type": m.meeting_type,
        "status": m.status,
        "datetime": m.meeting_datetime.isoformat() if m.meeting_datetime else None,
        "location": m.location,
        "bill_ids": m.bill_ids or [],
    }


@router.get("/{committee_id}/bills")
async def committee_referred_bills(
    committee_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    """Recent bills referred to the committee — fetched on demand from
    Congress.gov and joined to our stored titles (fail-soft: empty when a key or
    the source is unavailable, or for joint committees)."""
    return {"committee_id": committee_id, "bills": await referred_bills(db, committee_id)}
