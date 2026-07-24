from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict


def _date_only(v: Any) -> Any:
    # OpenFEC returns coverage dates as full timestamps
    # ("2023-01-01T00:00:00+00:00"); reduce to a plain date for a Date column.
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str) and "T" in v:
        return v.split("T", 1)[0]
    return v


FlexDate = Annotated[date | None, BeforeValidator(_date_only)]


class CandidateTotalRaw(BaseModel):
    """One cycle's row from GET /candidate/{candidate_id}/totals/ (the singular,
    per-candidate endpoint — NOT /candidates/totals/, which only reports itemized
    individual + PAC money and omits unitemized small-dollar, party, and the
    combined individual total). Only the persisted fields are modeled; the rest of
    the Form 3 line items are ignored.

    Field names below are OpenFEC's; the pipeline renames a few for storage
    (e.g. other_political_committee_contributions -> pac_contributions)."""

    cycle: int | None = None

    # Topline
    receipts: float | None = None
    disbursements: float | None = None
    cash_on_hand_end_period: float | None = None
    debts_owed_by_committee: float | None = None

    # Where the money came from (Form 3, Line 11 family)
    contributions: float | None = None  # total contributions
    individual_contributions: float | None = None  # itemized + unitemized combined
    individual_itemized_contributions: float | None = None  # large / disclosed donors
    individual_unitemized_contributions: float | None = None  # small-dollar (< $200)
    other_political_committee_contributions: float | None = None  # PACs
    political_party_committee_contributions: float | None = None  # party committees
    transfers_from_other_authorized_committee: float | None = None
    candidate_contribution: float | None = None  # self-funding
    other_receipts: float | None = None
    loans: float | None = None

    # Where the money went / gave back
    operating_expenditures: float | None = None
    refunded_individual_contributions: float | None = None

    coverage_start_date: FlexDate = None
    coverage_end_date: FlexDate = None

    model_config = ConfigDict(extra="ignore")


class ScheduleAItemRaw(BaseModel):
    """One itemized receipt from GET /schedules/schedule_a/ — 'who gave what,
    when'. sub_id is the FEC transaction id (stable dedupe key). Only display
    fields are modeled; the rest of the Schedule A row is ignored."""

    sub_id: str | None = None
    committee_id: str | None = None
    contributor_name: str | None = None
    contributor_employer: str | None = None
    contributor_occupation: str | None = None
    contributor_city: str | None = None
    contributor_state: str | None = None
    contribution_receipt_amount: float | None = None
    contribution_receipt_date: FlexDate = None
    contributor_aggregate_ytd: float | None = None

    model_config = ConfigDict(extra="ignore")
