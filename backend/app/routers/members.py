from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.member import Member
from app.schemas.member import MemberOut

router = APIRouter(prefix="/api/members", tags=["members"])


@router.get("", response_model=list[MemberOut])
async def list_members(
    db: AsyncSession = Depends(get_db),
    chamber: Literal["house", "senate"] | None = None,
    state: str | None = Query(default=None, min_length=2, max_length=2),
    party: str | None = None,
    limit: int = Query(default=100, le=535),
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
