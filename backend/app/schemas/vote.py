from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

# The official roll-call sources are XML (House Clerk EVS / Senate LIS), parsed
# manually in the pipelines into canonical dicts, so they have no Pydantic *Raw
# model. The Voteview Senate fallback is CSV and IS validated row-by-row below.


def _blank_to_none(v: Any) -> Any:
    return None if isinstance(v, str) and not v.strip() else v


OptInt = Annotated[int | None, BeforeValidator(_blank_to_none)]
OptStr = Annotated[str | None, BeforeValidator(_blank_to_none)]


# --- Layer 1: Voteview static CSVs (Senate fallback) ---
# https://voteview.com/data — one file per Congress. Every cell arrives as a
# string; Pydantic coerces ints/dates. Only the columns the pipeline uses are
# modeled; extras are ignored so an added column can't break the pull.


class VoteviewRollcallRaw(BaseModel):
    """One row of S{c}_rollcalls.csv. `rollnumber` is Voteview's Congress-wide
    sequence; `session` + `clerk_rollnumber` are the official Senate vote id."""

    congress: int = Field(ge=1)
    chamber: str
    rollnumber: int = Field(ge=1)
    vote_date: date = Field(alias="date")
    session: int = Field(ge=1, le=2)
    clerk_rollnumber: int = Field(ge=1)
    yea_count: OptInt = Field(default=None, ge=0)
    nay_count: OptInt = Field(default=None, ge=0)
    bill_number: OptStr = None
    vote_result: OptStr = None
    vote_question: OptStr = None

    model_config = ConfigDict(extra="ignore")


class VoteviewMemberRaw(BaseModel):
    """One row of S{c}_members.csv — the ICPSR id -> Bioguide bridge. The
    "President" row (presidential-support scores) has a blank bioguide_id."""

    congress: int = Field(ge=1)
    chamber: str
    icpsr: int = Field(ge=1)
    bioguide_id: OptStr = None

    model_config = ConfigDict(extra="ignore")


class VoteviewCastRaw(BaseModel):
    """One row of S{c}_votes.csv — how one member (by ICPSR) cast one roll call."""

    congress: int = Field(ge=1)
    chamber: str
    rollnumber: int = Field(ge=1)
    icpsr: int = Field(ge=1)
    cast_code: int = Field(ge=0, le=9)

    model_config = ConfigDict(extra="ignore")


class VoteviewPosition(BaseModel):
    bioguide_id: str = Field(pattern=r"^[A-Z]\d{6}$")
    position: Literal["Yea", "Nay", "Present", "Not Voting"]


class VoteviewStagedVote(BaseModel):
    """Validate reusable staging as well as downloaded data."""

    vote_id: str
    chamber: Literal["senate"]
    congress: int = Field(ge=1)
    session: int = Field(ge=1, le=2)
    roll_number: int = Field(ge=1)
    vote_date: date = Field(alias="date")
    question: str | None
    result: str | None = Field(max_length=120)
    bill_id: str | None
    totals: dict[str, int]
    source_url: str
    provenance: Literal["voteview"]
    positions: list[VoteviewPosition] = Field(min_length=1)


# --- Layer 3: API response shape ---


class VoteOut(BaseModel):
    vote_id: str
    chamber: str
    congress: int
    session: int
    roll_number: int
    date: date | None
    question: str | None
    result: str | None
    bill_id: str | None
    totals: dict | None

    model_config = ConfigDict(from_attributes=True)
