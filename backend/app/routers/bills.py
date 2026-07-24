import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.bill import Bill, BillAction, Cosponsor
from app.models.member import Member
from app.schemas.bill import BillOut
from app.services.bill_enrich import enrich_bill, get_bill_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bills", tags=["bills"])


@router.get("", response_model=list[BillOut])
async def list_bills(
    db: AsyncSession = Depends(get_db),
    congress: int | None = None,
    bill_type: str | None = None,
    sponsor: str | None = Query(default=None, description="sponsor bioguide_id"),
    policy_area: str | None = None,
    limit: int = Query(default=50, le=250),
    offset: int = 0,
) -> list[Bill]:
    # Most-recently-updated first — matches how the pipeline prioritizes and how
    # a "what's moving in Congress" view wants them.
    stmt = select(Bill).order_by(nullslast(Bill.update_date.desc()), Bill.bill_id)
    if congress:
        stmt = stmt.where(Bill.congress == congress)
    if bill_type:
        stmt = stmt.where(Bill.bill_type == bill_type.lower())
    if sponsor:
        stmt = stmt.where(Bill.sponsor_bioguide_id == sponsor)
    if policy_area:
        stmt = stmt.where(Bill.policy_area == policy_area)
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{bill_id}")
async def bill_detail(bill_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Full bill: core fields + sponsor name + action timeline + cosponsors.
    Cosponsor/sponsor names are left-joined from `members` and may be null for
    an actor no longer in the current-members table.

    On first view of a sponsored-legislation stub (title + sponsor only), this
    enriches it in place — pulling actions/cosponsors/summary/text — so the
    corpus fills in as people browse, not only for the ~250 recently-updated
    bills the scheduled pull covers."""
    # Fail-soft: a transient enrichment error must never block viewing the stub.
    try:
        await enrich_bill(db, bill_id)  # no-op if already enriched / missing / no key
    except Exception:
        await db.rollback()
        logger.warning("bill_detail: enrichment failed for %s (showing stub)", bill_id)

    bill = (
        await db.execute(select(Bill).where(Bill.bill_id == bill_id))
    ).scalar_one_or_none()
    if bill is None:
        raise HTTPException(status_code=404, detail="bill not found")

    sponsor = None
    if bill.sponsor_bioguide_id:
        sponsor_member = (
            await db.execute(
                select(
                    Member.bioguide_id,
                    Member.official_full_name,
                    Member.party,
                    Member.state,
                    Member.photo_url,
                ).where(Member.bioguide_id == bill.sponsor_bioguide_id)
            )
        ).first()
        sponsor = {
            "bioguide_id": bill.sponsor_bioguide_id,
            "official_full_name": sponsor_member.official_full_name if sponsor_member else None,
            "party": sponsor_member.party if sponsor_member else None,
            "state": sponsor_member.state if sponsor_member else None,
            "photo_url": sponsor_member.photo_url if sponsor_member else None,
        }

    actions = (
        await db.execute(
            select(BillAction).where(BillAction.bill_id == bill_id).order_by(BillAction.seq)
        )
    ).scalars().all()

    cosponsor_rows = (
        await db.execute(
            select(
                Cosponsor.bioguide_id,
                Cosponsor.sponsorship_date,
                Cosponsor.is_original,
                Member.official_full_name,
                Member.party,
                Member.state,
            )
            .outerjoin(Member, Member.bioguide_id == Cosponsor.bioguide_id)
            .where(Cosponsor.bill_id == bill_id)
            .order_by(nullslast(Cosponsor.sponsorship_date))
        )
    ).all()

    return {
        "bill_id": bill.bill_id,
        "congress": bill.congress,
        "bill_type": bill.bill_type,
        "number": bill.number,
        "title": bill.title,
        "introduced_date": bill.introduced_date.isoformat() if bill.introduced_date else None,
        "latest_action": bill.latest_action,
        "latest_action_date": bill.latest_action_date.isoformat() if bill.latest_action_date else None,
        "status": bill.status,
        "policy_area": bill.policy_area,
        "update_date": bill.update_date.isoformat() if bill.update_date else None,
        "summary": bill.summary,
        "summary_date": bill.summary_date.isoformat() if bill.summary_date else None,
        "text_url": bill.text_url,
        "text_version": bill.text_version,
        "sponsor": sponsor,
        "actions": [
            {
                "seq": a.seq,
                "action_date": a.action_date.isoformat() if a.action_date else None,
                "chamber": a.chamber,
                "text": a.text,
                "action_type": a.action_type,
            }
            for a in actions
        ],
        "cosponsors": [
            {
                "bioguide_id": r.bioguide_id,
                "official_full_name": r.official_full_name,
                "party": r.party,
                "state": r.state,
                "sponsorship_date": r.sponsorship_date.isoformat() if r.sponsorship_date else None,
                "is_original": r.is_original,
            }
            for r in cosponsor_rows
        ],
    }


@router.get("/{bill_id}/text")
async def bill_full_text(bill_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """The bill's full legislative text as plain text for in-platform rendering,
    fetched from the official GPO/govinfo 'Formatted Text' version on first view
    and cached. 404 when the bill is unknown or has no readable text version yet
    (e.g. only a PDF exists, or text isn't published)."""
    text = await get_bill_text(db, bill_id)
    if text is None:
        raise HTTPException(status_code=404, detail="no in-app text available for this bill")
    return text
