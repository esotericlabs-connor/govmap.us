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


# --- Layer 3: API response shapes ---


class CommitteeOut(BaseModel):
    committee_id: str
    name: str
    chamber: str
    committee_type: str | None
    parent_committee_id: str | None
    url: str | None

    model_config = ConfigDict(from_attributes=True)
