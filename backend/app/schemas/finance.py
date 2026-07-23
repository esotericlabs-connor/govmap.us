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
    """One cycle's row from GET /candidate/{candidate_id}/totals/. Only the
    persisted fields are modeled; extras are ignored."""

    cycle: int | None = None
    receipts: float | None = None
    disbursements: float | None = None
    cash_on_hand_end_period: float | None = None
    debts_owed_by_committee: float | None = None
    individual_contributions: float | None = None
    other_political_committee_contributions: float | None = None
    political_party_committee_contributions: float | None = None
    coverage_start_date: FlexDate = None
    coverage_end_date: FlexDate = None

    model_config = ConfigDict(extra="ignore")
