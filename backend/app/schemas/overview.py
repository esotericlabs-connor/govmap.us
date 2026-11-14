"""Response shape for GET /api/overview, the federal dashboard snapshot.

Every series carries what it covers, so the UI can tell "no activity" apart
from "not collected": a null weekly count means that week is outside the stored
records, never zero.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class ChamberBalanceOut(BaseModel):
    """In-office members by party bucket, delegates included (as /api/summary)."""

    D: int
    R: int
    # The party letter, matching /api/summary.
    I: int  # noqa: E741
    total: int


class ChambersOut(BaseModel):
    house: ChamberBalanceOut
    senate: ChamberBalanceOut


class WeeklyVotesOut(BaseModel):
    """Roll calls per week, aligned with ActivityOut.weeks; null = not collected."""

    house: list[int | None]
    senate: list[int | None]


class VoteCoverageOut(BaseModel):
    """Date of the earliest stored roll call per chamber (null = none stored)."""

    house: date | None
    senate: date | None


class ActivityOut(BaseModel):
    # Monday of each week, oldest first. The last week is the current one, so
    # its counts are week-to-date.
    weeks: list[date]
    votes: WeeklyVotesOut
    votes_covered_from: VoteCoverageOut
    # Current-Congress bills GovMap holds, by introduced date: everything
    # sponsored by current members plus recently updated bills.
    bills_introduced: list[int]


class MeetingOut(BaseModel):
    event_id: str
    committee_id: str
    committee_name: str
    chamber: str | None
    title: str | None
    meeting_type: str | None
    # As published: Scheduled, Canceled, Postponed or Rescheduled.
    status: str | None
    starts_at: datetime


class SourceFreshnessOut(BaseModel):
    name: str
    title: str
    publisher: str
    # Last successful refresh; null when it has never succeeded.
    last_success: datetime | None


class OverviewOut(BaseModel):
    congress: int = Field(ge=1)
    generated_at: datetime
    chambers: ChambersOut
    activity: ActivityOut
    bills_in_congress: int
    laws_enacted: int
    upcoming_meetings: list[MeetingOut]
    sources: list[SourceFreshnessOut]
