from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.finance import MemberFinance
from app.models.member import Member
from app.services.donations import get_donation_cycles, get_donations
from app.types import BioguideId

router = APIRouter(prefix="/api/members", tags=["donations"])


async def _require_member(db: AsyncSession, bioguide_id: str) -> None:
    member = await db.get(Member, bioguide_id)
    if member is None:
        raise HTTPException(status_code=404, detail="member not found")


@router.get("/{bioguide_id}/donations/cycles")
async def member_donation_cycles(
    bioguide_id: BioguideId,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The election cycles a member's itemized donations can be browsed for
    (newest first), backing the ledger's cycle picker."""
    await _require_member(db, bioguide_id)
    cycles = await get_donation_cycles(db, bioguide_id)
    return {"cycles": cycles, "default": cycles[0] if cycles else settings.fec_cycle}


@router.get("/{bioguide_id}/donations")
async def member_donations(
    bioguide_id: BioguideId,
    db: AsyncSession = Depends(get_db),
    cycle: int | None = Query(default=None, ge=1976, le=2100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    sort: str = "amount",
    q: str | None = Query(default=None, max_length=100),
) -> dict:
    """A member's itemized FEC donations ledger (disclosed receipts ≥ $200),
    cached on demand from the FEC. `sort` (amount|amount_asc|date|date_asc|name)
    and `q` (search contributor/employer/city) filter the cached rows. Defaults
    to the cycle on the member's finance card (their latest with totals), else
    the current cycle."""
    if cycle is not None and (cycle % 2 or cycle > settings.fec_cycle):
        raise HTTPException(status_code=422, detail="cycle must be an even year no later than the current FEC cycle")
    await _require_member(db, bioguide_id)
    if cycle is None:
        cycle = (
            await db.execute(
                select(MemberFinance.cycle)
                .where(MemberFinance.bioguide_id == bioguide_id)
                .order_by(MemberFinance.cycle.desc())
            )
        ).scalars().first() or settings.fec_cycle
    return await get_donations(db, bioguide_id, cycle, offset, limit, sort=sort, q=q)
