from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

ElectionOffice = Literal["H", "S", "P"]


class FecPrincipalCommitteeRaw(BaseModel):
    """Publisher-provided principal committee metadata, retained as received."""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class FecCandidateRaw(BaseModel):
    """Candidate fields returned by OpenFEC GET /candidates/."""

    candidate_id: str = Field(min_length=1, max_length=20)
    name: str | None = Field(default=None, max_length=100)
    office: ElectionOffice | None = None
    office_full: str | None = Field(default=None, max_length=20)
    state: str | None = Field(default=None, max_length=2)
    district: str | None = Field(default=None, max_length=2)
    party: str | None = Field(default=None, max_length=3)
    party_full: str | None = Field(default=None, max_length=255)
    candidate_status: str | None = Field(default=None, max_length=1)
    incumbent_challenge: str | None = Field(default=None, max_length=1)
    first_file_date: date | None = None
    last_file_date: date | None = None
    cycles: list[int] | None = None
    election_years: list[int] | None = None
    principal_committees: list[FecPrincipalCommitteeRaw] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class FecCandidatePageRaw(BaseModel):
    results: list[FecCandidateRaw]
    pagination: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class FecCandidateSnapshotRaw(BaseModel):
    source: Literal["fec_candidates"]
    finance_cycle: int = Field(ge=1979, le=2100)
    complete: bool
    candidate_count: int = Field(ge=0)
    expected_count: int | None = Field(default=None, ge=0)
    page_count: int = Field(ge=1)
    snapshot_revision: str = Field(min_length=64, max_length=64)
    fetched_at: datetime
    candidates: list[FecCandidateRaw]

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ElectionCandidateOut(BaseModel):
    candidate_id: str
    finance_cycle: int
    name: str | None
    office: ElectionOffice | None
    office_full: str | None
    state: str | None
    district: str | None
    party: str | None
    party_full: str | None
    candidate_status: str | None
    incumbent_challenge: str | None
    first_file_date: date | None
    last_file_date: date | None
    cycles: list[int]
    election_years: list[int]
    principal_committees: list[FecPrincipalCommitteeRaw]

    model_config = ConfigDict(from_attributes=True)


class CandidateGroupingOut(BaseModel):
    office: ElectionOffice | None
    office_full: str | None
    state: str | None
    district: str | None
    candidate_count: int


class ElectionCandidatesOut(BaseModel):
    finance_cycle: int
    available: bool
    complete: bool
    candidate_count: int
    expected_count: int | None
    fetched_at: datetime | None
    filtered_count: int
    limit: int
    offset: int
    groupings: list[CandidateGroupingOut]
    candidates: list[ElectionCandidateOut]


class FecCalendarEventRaw(BaseModel):
    """FEC calendar events in the publisher's Election Dates category."""

    all_day: bool
    calendar_category_id: Literal[36]
    category: Literal["Election Dates"]
    description: str | None = Field(default=None, max_length=4000)
    end_date: date | None = None
    event_id: int = Field(gt=0)
    location: str | None = Field(default=None, max_length=255)
    start_date: date
    state: list[str] | None = None
    summary: str = Field(min_length=1, max_length=255)
    url: HttpUrl | None = None

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class FecCalendarPageRaw(BaseModel):
    results: list[FecCalendarEventRaw]
    pagination: dict[str, object]

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class FecCalendarSnapshotRaw(BaseModel):
    source: Literal["fec_election_calendar"]
    calendar_year: int = Field(ge=1979, le=2100)
    complete: bool
    expected_count: int = Field(ge=1)
    page_count: int = Field(ge=1)
    snapshot_revision: str = Field(min_length=64, max_length=64)
    fetched_at: datetime
    events: list[FecCalendarEventRaw]

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ElectionCalendarEventOut(BaseModel):
    calendar_year: int
    event_id: int
    category: str
    summary: str
    description: str | None
    location: str | None
    state: list[str]
    start_date: date
    end_date: date | None
    url: HttpUrl | None

    model_config = ConfigDict(from_attributes=True)


class ElectionCalendarOut(BaseModel):
    calendar_year: int
    available: bool
    complete: bool
    event_count: int
    expected_count: int | None
    fetched_at: datetime | None
    events: list[ElectionCalendarEventOut]
