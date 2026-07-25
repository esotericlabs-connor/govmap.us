from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.finance import MemberFinance
from app.services.donations import get_donations

router = APIRouter(prefix="/api/members", tags=["donations"])


@router.get("/{bioguide_id}/donations")
async def member_donations(
    bioguide_id: str,
    db: AsyncSession = Depends(get_db),
    cycle: int | None = None,
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
    if cycle is None:
        cycle = (
            await db.execute(
                select(MemberFinance.cycle)
                .where(MemberFinance.bioguide_id == bioguide_id)
                .order_by(MemberFinance.cycle.desc())
            )
        ).scalars().first() or settings.fec_cycle
    return await get_donations(db, bioguide_id, cycle, offset, limit, sort=sort, q=q)
