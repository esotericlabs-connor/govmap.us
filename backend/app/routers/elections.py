from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.election import (
    ElectionCalendarCoverage,
    ElectionCalendarEvent,
    ElectionCandidate,
    ElectionCatalogCoverage,
)
from app.schemas.election import ElectionCalendarOut, ElectionCandidatesOut
from app.types import MAX_LIST_OFFSET

router = APIRouter(prefix="/api/elections", tags=["elections"])


@router.get("/calendar", response_model=ElectionCalendarOut)
async def list_election_calendar(
    db: AsyncSession = Depends(get_db),
    year: int = Query(default=settings.fec_cycle, ge=1979, le=2100),
) -> ElectionCalendarOut:
    coverage = (
        await db.execute(
            select(ElectionCalendarCoverage).where(
                ElectionCalendarCoverage.calendar_year == year
            )
        )
    ).scalar_one_or_none()

    if coverage is None:
        return ElectionCalendarOut(
            generated_at=datetime.now(UTC),
            calendar_year=year,
            available=False,
            complete=False,
            event_count=0,
            expected_count=None,
            fetched_at=None,
            events=[],
        )

    events = (
        await db.execute(
            select(ElectionCalendarEvent)
            .where(ElectionCalendarEvent.calendar_year == year)
            .order_by(ElectionCalendarEvent.start_date, ElectionCalendarEvent.event_id)
        )
    ).scalars().all()

    return ElectionCalendarOut(
        generated_at=datetime.now(UTC),
        calendar_year=year,
        available=True,
        complete=coverage.complete,
        event_count=coverage.event_count,
        expected_count=coverage.expected_count,
        fetched_at=coverage.fetched_at,
        events=events,
    )


@router.get("/candidates", response_model=ElectionCandidatesOut)
async def list_election_candidates(
    db: AsyncSession = Depends(get_db),
    cycle: int = Query(default=settings.fec_cycle, ge=1979, le=2100),
    election_year: int | None = Query(default=None, ge=1979, le=2100),
    office: Literal["H", "S", "P"] | None = None,
    state: str | None = Query(default=None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$"),
    district: str | None = Query(
        default=None, min_length=2, max_length=2, pattern=r"^[0-9]{2}$"
    ),
    party: str | None = Query(default=None, min_length=1, max_length=3),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=MAX_LIST_OFFSET),
) -> ElectionCandidatesOut:
    coverage = (
        await db.execute(
            select(ElectionCatalogCoverage).where(
                ElectionCatalogCoverage.finance_cycle == cycle
            )
        )
    ).scalar_one_or_none()

    if coverage is None:
        return ElectionCandidatesOut(
            generated_at=datetime.now(UTC),
            finance_cycle=cycle,
            available=False,
            complete=False,
            candidate_count=0,
            expected_count=None,
            fetched_at=None,
            filtered_count=0,
            limit=limit,
            offset=offset,
            groupings=[],
            candidates=[],
        )

    filters = [ElectionCandidate.finance_cycle == cycle]
    if election_year is not None:
        filters.append(ElectionCandidate.election_years.any(election_year))
    if office is not None:
        filters.append(ElectionCandidate.office == office)
    if state is not None:
        filters.append(ElectionCandidate.state == state.upper())
    if district is not None:
        filters.append(ElectionCandidate.district == district)
    if party is not None:
        filters.append(ElectionCandidate.party == party.upper())
    if q is not None and q.strip():
        filters.append(ElectionCandidate.name.ilike(f"%{q.strip()}%"))

    filtered_count = (
        await db.execute(
            select(func.count())
            .select_from(ElectionCandidate)
            .where(*filters)
        )
    ).scalar_one()

    grouping_rows = (
        await db.execute(
            select(
                ElectionCandidate.office,
                ElectionCandidate.office_full,
                ElectionCandidate.state,
                ElectionCandidate.district,
                func.count(ElectionCandidate.candidate_id).label("candidate_count"),
            )
            .where(*filters)
            .group_by(
                ElectionCandidate.office,
                ElectionCandidate.office_full,
                ElectionCandidate.state,
                ElectionCandidate.district,
            )
            .order_by(
                ElectionCandidate.office,
                ElectionCandidate.state,
                ElectionCandidate.district,
            )
            .limit(600)
        )
    ).all()

    candidate_rows = (
        await db.execute(
            select(ElectionCandidate)
            .where(*filters)
            .order_by(
                ElectionCandidate.office,
                ElectionCandidate.state,
                ElectionCandidate.district,
                ElectionCandidate.name,
                ElectionCandidate.candidate_id,
            )
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    return ElectionCandidatesOut(
        generated_at=datetime.now(UTC),
        finance_cycle=cycle,
        available=True,
        complete=coverage.complete,
        candidate_count=coverage.candidate_count,
        expected_count=coverage.expected_count,
        fetched_at=coverage.fetched_at,
        filtered_count=filtered_count,
        limit=limit,
        offset=offset,
        groupings=[
            {
                "office": row.office,
                "office_full": row.office_full,
                "state": row.state,
                "district": row.district,
                "candidate_count": row.candidate_count,
            }
            for row in grouping_rows
        ],
        candidates=candidate_rows,
    )
