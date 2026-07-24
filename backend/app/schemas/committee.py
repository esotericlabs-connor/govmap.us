from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --- Layer 1: raw shapes from committees-current.yaml and
# committee-membership-current.yaml (unitedstates/congress-legislators) ---


class SubcommitteeRaw(BaseModel):
    name: str
    thomas_id: str  # 2-digit; full id = parent thomas_id + this

    model_config = ConfigDict(extra="ignore")


class CommitteeRaw(BaseModel):
    type: Literal["house", "senate", "joint"]
    name: str
    thomas_id: str
    url: str | None = None
    subcommittees: list[SubcommitteeRaw] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class CommitteeMemberRaw(BaseModel):
    name: str
    party: str  # "majority" | "minority"
    bioguide: str | None = None  # skip entries without one — can't join
    rank: int | None = None
    title: str | None = None  # e.g. "Chairman", "Ranking Member"

    model_config = ConfigDict(extra="ignore")


# --- Layer 1: raw shapes from Congress.gov /committee-meeting (JSON) ---
# Modeled against the JSON responses, which return direct arrays (not the
# `.item`-wrapped XML the docs show) — same convention as the bills schemas.


class MeetingCommitteeRaw(BaseModel):
    systemCode: str | None = None
    name: str | None = None

    model_config = ConfigDict(extra="ignore")


class MeetingLocationRaw(BaseModel):
    building: str | None = None
    room: str | None = None
    address: str | None = None

    model_config = ConfigDict(extra="ignore")


class MeetingBillRaw(BaseModel):
    congress: int | None = None
    type: str | None = None
    number: int | None = None  # JSON string, coerced to int like BillListItemRaw

    model_config = ConfigDict(extra="ignore")


class MeetingRelatedItemsRaw(BaseModel):
    bills: list[MeetingBillRaw] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class CommitteeMeetingRaw(BaseModel):
    """The `committeeMeeting` object from
    GET /committee-meeting/{congress}/{chamber}/{eventId}. All fields optional —
    a meeting missing a date or committee is skipped by the normalizer."""

    eventId: str | None = None
    title: str | None = None
    type: str | None = None  # Meeting | Hearing | Markup
    meetingStatus: str | None = None  # Scheduled | Canceled | Postponed | Rescheduled
    date: datetime | None = None
    chamber: str | None = None
    committees: list[MeetingCommitteeRaw] = Field(default_factory=list)
    location: MeetingLocationRaw | None = None
    relatedItems: MeetingRelatedItemsRaw | None = None

    model_config = ConfigDict(extra="ignore")


# --- Layer 3: API response shapes ---


class CommitteeOut(BaseModel):
    committee_id: str
    name: str
    chamber: str
    committee_type: str | None
    parent_committee_id: str | None
    url: str | None

    model_config = ConfigDict(from_attributes=True)
