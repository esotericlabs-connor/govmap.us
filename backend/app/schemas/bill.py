from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

# --- Layer 1: raw shapes from the Congress.gov v3 API (format=json) ---
# https://api.congress.gov/ — modeled against the *JSON* responses, which differ
# from the XML-derived docs: `sponsors` and `laws` come back as direct arrays
# (not `.item`-wrapped) and collections paginate via `pagination.next`. Bill
# `number` arrives as a JSON string but is always integral, so it's typed `int`
# (Pydantic coerces "3076" -> 3076). Only persisted fields are modeled; extras
# are ignored so an upstream addition can't break the pull.


def _date_only(v: Any) -> Any:
    # The detail endpoint returns `updateDate` as a full timestamp
    # ("2026-07-22T08:09:17Z"), not the date-only value the docs show. Reduce any
    # datetime / ISO-datetime string to a plain date so a Date field accepts it.
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str) and "T" in v:
        return v.split("T", 1)[0]
    return v


# A date field tolerant of the API's occasional datetime-with-time values.
FlexDate = Annotated[date | None, BeforeValidator(_date_only)]


class BillListItemRaw(BaseModel):
    """One entry from GET /bill/{congress} — enough to identify a bill for the
    detail fetch that follows."""

    congress: int
    type: str  # "HR", "S", "HRES", "SJRES", ...
    number: int

    model_config = ConfigDict(extra="ignore")


class SponsorRaw(BaseModel):
    bioguideId: str | None = None
    fullName: str | None = None
    party: str | None = None
    state: str | None = None

    model_config = ConfigDict(extra="ignore")


class PolicyAreaRaw(BaseModel):
    name: str | None = None

    model_config = ConfigDict(extra="ignore")


class LatestActionRaw(BaseModel):
    actionDate: FlexDate = None
    text: str | None = None

    model_config = ConfigDict(extra="ignore")


class LawRaw(BaseModel):
    type: str | None = None
    number: str | None = None

    model_config = ConfigDict(extra="ignore")


class BillDetailRaw(BaseModel):
    """GET /bill/{congress}/{type}/{number} — the `bill` object."""

    congress: int
    type: str
    number: int
    title: str | None = None
    introducedDate: FlexDate = None
    updateDate: FlexDate = None
    originChamber: str | None = None
    policyArea: PolicyAreaRaw | None = None
    sponsors: list[SponsorRaw] = Field(default_factory=list)
    latestAction: LatestActionRaw | None = None
    laws: list[LawRaw] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class SourceSystemRaw(BaseModel):
    code: str | int | None = None
    name: str | None = None  # "House" | "Senate" | "Library of Congress"

    model_config = ConfigDict(extra="ignore")


class BillActionRaw(BaseModel):
    """GET /bill/{congress}/{type}/{number}/actions — one action."""

    actionDate: FlexDate = None
    text: str
    type: str | None = None
    sourceSystem: SourceSystemRaw | None = None

    model_config = ConfigDict(extra="ignore")


class CosponsorRaw(BaseModel):
    """GET /bill/{congress}/{type}/{number}/cosponsors — one cosponsor."""

    bioguideId: str | None = None
    sponsorshipDate: FlexDate = None
    isOriginalCosponsor: bool | None = None

    model_config = ConfigDict(extra="ignore")


# --- Layer 3: API response shape ---


class BillOut(BaseModel):
    bill_id: str
    congress: int
    bill_type: str
    number: int
    title: str | None
    sponsor_bioguide_id: str | None
    introduced_date: date | None
    latest_action: str | None
    latest_action_date: date | None
    status: str | None
    policy_area: str | None
    update_date: date | None

    model_config = ConfigDict(from_attributes=True)
