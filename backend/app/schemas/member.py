from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Layer 1: raw shape pulled from unitedstates/congress-legislators ---
# https://github.com/unitedstates/congress-legislators — only the fields
# the pilot pipeline needs are modeled here; extra source fields are ignored
# rather than rejected, so the pipeline doesn't break when upstream adds one.


class LegislatorId(BaseModel):
    bioguide: str
    fec: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class LegislatorName(BaseModel):
    first: str
    last: str
    official_full: str | None = None

    model_config = ConfigDict(extra="ignore")


class LegislatorTerm(BaseModel):
    type: Literal["rep", "sen"]
    start: date
    end: date
    state: str
    district: int | None = None
    party: str

    model_config = ConfigDict(extra="ignore")


class LegislatorRaw(BaseModel):
    id: LegislatorId
    name: LegislatorName
    terms: list[LegislatorTerm]

    model_config = ConfigDict(extra="ignore")

    @field_validator("terms")
    @classmethod
    def terms_not_empty(cls, v: list[LegislatorTerm]) -> list[LegislatorTerm]:
        if not v:
            raise ValueError("legislator record has no terms")
        return v


# --- Layer 3: normalized API response shape (subset of the canonical
# members.json fields — the rest arrive once the images/FEC/committee
# pipelines are built; see CODE-MANIFEST.md) ---


class MemberOut(BaseModel):
    bioguide_id: str
    first_name: str
    last_name: str
    official_full_name: str
    chamber: Literal["house", "senate"]
    state: str
    district: int | None
    party: str
    term_start: date
    fec_candidate_ids: list[str]
    photo_url: str | None

    model_config = ConfigDict(from_attributes=True)
