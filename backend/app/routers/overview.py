"""Federal overview: one compact, read-only snapshot behind the dashboard at `/`.

Derived entirely from tables the existing pipelines already load, so it adds
no upstream calls. What each series covers is documented on its response model
(app.schemas.overview); the dashboard shows that coverage next to the numbers.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.bill import Bill
from app.models.committee import Committee, CommitteeMeeting
from app.models.vote import Vote
from app.routers.congress import chamber_balance
from app.routers.data_sources import last_successes
from app.schemas.overview import (
    ActivityOut,
    ChambersOut,
    MeetingOut,
    OverviewOut,
    SourceFreshnessOut,
    VoteCoverageOut,
    WeeklyVotesOut,
)
from app.sources import SOURCES

router = APIRouter(prefix="/api", tags=["overview"])

DEFAULT_WEEKS = 12
MIN_WEEKS = 4
MAX_WEEKS = 52
MEETINGS_LIMIT = 6


def week_start(day: date) -> date:
    """Monday of the week containing `day`."""
    return day - timedelta(days=day.weekday())


async def _weekly_votes(
    db: AsyncSession, weeks: list[date], today: date
) -> tuple[WeeklyVotesOut, VoteCoverageOut]:
    # The vote pipelines keep accumulating the latest roll calls per chamber,
    # so records are complete from each chamber's earliest stored vote onward.
    covered: dict[str, date] = {
        chamber: first
        for chamber, first in (
            await db.execute(
                select(Vote.chamber, func.min(Vote.date))
                .where(Vote.date.is_not(None))
                .group_by(Vote.chamber)
            )
        ).all()
    }
    position = {week: i for i, week in enumerate(weeks)}
    counts = {"house": [0] * len(weeks), "senate": [0] * len(weeks)}
    rows = (
        await db.execute(
            select(Vote.chamber, Vote.date, func.count())
            .where(Vote.date >= weeks[0], Vote.date <= today)
            .group_by(Vote.chamber, Vote.date)
        )
    ).all()
    for chamber, day, n in rows:
        if chamber in counts:
            counts[chamber][position[week_start(day)]] += n

    def series(chamber: str) -> list[int | None]:
        start = covered.get(chamber)
        # A week that ended before the first stored vote was never collected.
        return [
            None if start is None or week + timedelta(days=6) < start else n
            for week, n in zip(weeks, counts[chamber], strict=True)
        ]

    return (
        WeeklyVotesOut(house=series("house"), senate=series("senate")),
        VoteCoverageOut(house=covered.get("house"), senate=covered.get("senate")),
    )


async def _weekly_bills(
    db: AsyncSession, congress: int, weeks: list[date], today: date
) -> list[int]:
    position = {week: i for i, week in enumerate(weeks)}
    counts = [0] * len(weeks)
    rows = (
        await db.execute(
            select(Bill.introduced_date, func.count())
            .where(
                Bill.congress == congress,
                Bill.introduced_date >= weeks[0],
                Bill.introduced_date <= today,
            )
            .group_by(Bill.introduced_date)
        )
    ).all()
    for day, n in rows:
        counts[position[week_start(day)]] += n
    return counts


async def _upcoming_meetings(db: AsyncSession, now: datetime) -> list[MeetingOut]:
    # A meeting shared by a committee and its subcommittee is stored under both;
    # list it once. Parent ids sort before their subcommittees' (HSAG < HSAG15).
    rows = (
        await db.execute(
            select(
                CommitteeMeeting.event_id,
                CommitteeMeeting.committee_id,
                Committee.name,
                CommitteeMeeting.chamber,
                CommitteeMeeting.title,
                CommitteeMeeting.meeting_type,
                CommitteeMeeting.status,
                CommitteeMeeting.meeting_datetime,
            )
            .join(Committee, Committee.committee_id == CommitteeMeeting.committee_id)
            .where(CommitteeMeeting.meeting_datetime >= now)
            .order_by(
                CommitteeMeeting.meeting_datetime,
                CommitteeMeeting.event_id,
                CommitteeMeeting.committee_id,
            )
            .limit(MEETINGS_LIMIT * 4)
        )
    ).all()
    meetings: list[MeetingOut] = []
    seen: set[str] = set()
    for row in rows:
        if row.event_id in seen:
            continue
        seen.add(row.event_id)
        meetings.append(
            MeetingOut(
                event_id=row.event_id,
                committee_id=row.committee_id,
                committee_name=row.name,
                chamber=row.chamber,
                title=row.title,
                meeting_type=row.meeting_type,
                status=row.status,
                starts_at=row.meeting_datetime,
            )
        )
        if len(meetings) == MEETINGS_LIMIT:
            break
    return meetings


async def _source_freshness(db: AsyncSession) -> list[SourceFreshnessOut]:
    # Only registered sources, and only when each last succeeded.
    last_success = await last_successes(db)
    return [
        SourceFreshnessOut(
            name=spec.name,
            title=spec.title,
            publisher=spec.publisher,
            last_success=last_success.get(spec.name),
        )
        for spec in SOURCES.values()
    ]


async def build_overview(
    db: AsyncSession, *, weeks: int, now: datetime, congress: int
) -> OverviewOut:
    today = now.astimezone(UTC).date()
    current = week_start(today)
    week_starts = [current - timedelta(weeks=weeks - 1 - i) for i in range(weeks)]

    votes, covered_from = await _weekly_votes(db, week_starts, today)
    bills_in_congress, laws_enacted = (
        await db.execute(
            select(func.count(), func.count().filter(Bill.status == "Became Law")).where(
                Bill.congress == congress
            )
        )
    ).one()
    return OverviewOut(
        congress=congress,
        generated_at=now,
        chambers=ChambersOut.model_validate(await chamber_balance(db)),
        activity=ActivityOut(
            weeks=week_starts,
            votes=votes,
            votes_covered_from=covered_from,
            bills_introduced=await _weekly_bills(db, congress, week_starts, today),
        ),
        bills_in_congress=bills_in_congress,
        laws_enacted=laws_enacted,
        upcoming_meetings=await _upcoming_meetings(db, now),
        sources=await _source_freshness(db),
    )


@router.get("/overview", response_model=OverviewOut)
async def overview(
    weeks: int = Query(DEFAULT_WEEKS, ge=MIN_WEEKS, le=MAX_WEEKS),
    db: AsyncSession = Depends(get_db),
) -> OverviewOut:
    """Chamber balance, weekly legislative activity, laws enacted, upcoming
    committee meetings and source freshness for the current Congress."""
    return await build_overview(
        db, weeks=weeks, now=datetime.now(UTC), congress=settings.congress_number
    )
