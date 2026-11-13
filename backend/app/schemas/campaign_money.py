from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field

Amount = Annotated[Decimal, Field(max_digits=14, decimal_places=2, allow_inf_nan=False)]
Office = Literal["H", "S", "P"]


class FecCandidateFinanceRaw(BaseModel):
    """One FEC all-candidates financial summary, not an individual donation."""

    candidate_id: str = Field(pattern=r"^[HSP][A-Z0-9]{8}$")
    name: str | None = Field(default=None, max_length=200)
    office: Office
    state: str | None = Field(default=None, max_length=2)
    district: str | None = Field(default=None, max_length=2)
    party: str | None = Field(default=None, max_length=3)
    incumbent_challenge: str | None = Field(default=None, max_length=1)
    receipts: Amount | None = None
    transfers_from_authorized: Amount | None = None
    disbursements: Amount | None = None
    transfers_to_authorized: Amount | None = None
    cash_beginning: Amount | None = None
    cash_on_hand: Amount | None = None
    candidate_contributions: Amount | None = None
    candidate_loans: Amount | None = None
    other_loans: Amount | None = None
    candidate_loan_repayments: Amount | None = None
    other_loan_repayments: Amount | None = None
    debts: Amount | None = None
    individual_contributions: Amount | None = None
    other_committee_contributions: Amount | None = None
    party_contributions: Amount | None = None
    individual_refunds: Amount | None = None
    committee_refunds: Amount | None = None
    coverage_end: date | None = None

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class FecCommitteeLinkRaw(BaseModel):
    """An FEC linkage row; some source subjects are committees, not candidates."""

    subject_id: str = Field(pattern=r"^[A-Z0-9]{9}$")
    candidate_election_year: int = Field(ge=0, le=9999)
    fec_election_year: int = Field(ge=1900, le=2100)
    committee_id: str | None = Field(default=None, pattern=r"^C[A-Z0-9]{8}$")
    committee_type: str | None = Field(default=None, max_length=1)
    designation: str | None = Field(default=None, max_length=1)
    linkage_id: int = Field(ge=0, le=999_999_999_999)

    model_config = ConfigDict(extra="forbid")


class FecBulkFileRaw(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    last_modified: AwareDatetime | None = None

    model_config = ConfigDict(extra="forbid")


class FecCampaignMoneySnapshotRaw(BaseModel):
    source: Literal["fec_candidate_totals"]
    finance_cycle: int = Field(ge=2000, le=2098, multiple_of=2)
    complete: bool
    candidate_count: int = Field(gt=0)
    linkage_count: int = Field(gt=0)
    summary_file: FecBulkFileRaw
    linkage_file: FecBulkFileRaw
    snapshot_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    fetched_at: AwareDatetime
    candidates: list[FecCandidateFinanceRaw]
    linkages: list[FecCommitteeLinkRaw]

    model_config = ConfigDict(extra="forbid")


class CandidateFinanceOut(FecCandidateFinanceRaw):
    finance_cycle: int

    model_config = ConfigDict(from_attributes=True, extra="forbid", allow_inf_nan=False)


class CommitteeLinkOut(FecCommitteeLinkRaw):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @computed_field
    @property
    def candidate_election_year_outside_supported_range(self) -> bool:
        return not 1900 <= self.candidate_election_year <= 2100


class CampaignMoneyCoverageOut(BaseModel):
    finance_cycle: int
    candidate_count: int
    linkage_count: int
    summary_sha256: str
    summary_last_modified: datetime | None
    linkage_sha256: str
    linkage_last_modified: datetime | None
    snapshot_revision: str
    fetched_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportingDateOut(BaseModel):
    coverage_end: date
    candidate_count: int


class CandidateMoneyListOut(BaseModel):
    generated_at: datetime
    finance_cycle: int
    available: bool
    coverage: CampaignMoneyCoverageOut | None
    matching_count: int
    filtered_count: int
    reporting_dates: list[ReportingDateOut]
    reporting_dates_truncated: bool
    selected_date: date | None
    limit: int
    offset: int
    candidates: list[CandidateFinanceOut]


class CatalogMatchOut(BaseModel):
    candidate_status: str | None
    election_years: list[int]
    state: str | None
    district: str | None

    model_config = ConfigDict(from_attributes=True)


class CandidateMoneyDetailOut(BaseModel):
    generated_at: datetime
    coverage: CampaignMoneyCoverageOut
    candidate: CandidateFinanceOut
    catalog_match: CatalogMatchOut | None
    linkage_count: int
    limit: int
    offset: int
    linkages: list[CommitteeLinkOut]
