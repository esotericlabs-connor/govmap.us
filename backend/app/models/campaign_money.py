from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CandidateFinanceSummary(Base):
    """FEC candidate-level gross totals, retained separately from member floats."""

    __tablename__ = "candidate_finance_summaries"

    finance_cycle: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(9), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    office: Mapped[str] = mapped_column(String(1), nullable=False)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    district: Mapped[str | None] = mapped_column(String(2), nullable=True)
    party: Mapped[str | None] = mapped_column(String(3), nullable=True)
    incumbent_challenge: Mapped[str | None] = mapped_column(String(1), nullable=True)
    receipts: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    transfers_from_authorized: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    disbursements: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    transfers_to_authorized: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cash_beginning: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cash_on_hand: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    candidate_contributions: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    candidate_loans: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    other_loans: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    candidate_loan_repayments: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    other_loan_repayments: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    debts: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    individual_contributions: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    other_committee_contributions: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    party_contributions: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    individual_refunds: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    committee_refunds: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    coverage_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        CheckConstraint("office IN ('H', 'S', 'P')", name="ck_candidate_finance_office"),
        Index(
            "ix_candidate_finance_filters",
            "finance_cycle",
            "office",
            "state",
            "district",
            "coverage_end",
        ),
    )


class CandidateCommitteeLink(Base):
    """Publisher linkage; subject_id is not necessarily a candidate ID."""

    __tablename__ = "candidate_committee_links"

    finance_cycle: Mapped[int] = mapped_column(Integer, primary_key=True)
    linkage_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(9), nullable=False)
    candidate_election_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fec_election_year: Mapped[int] = mapped_column(Integer, nullable=False)
    committee_id: Mapped[str | None] = mapped_column(String(9), nullable=True)
    committee_type: Mapped[str | None] = mapped_column(String(1), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(1), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "fec_election_year = finance_cycle", name="ck_candidate_link_finance_cycle"
        ),
        Index("ix_candidate_committee_links_subject", "finance_cycle", "subject_id"),
    )


class CampaignMoneyCoverage(Base):
    """Provenance of the last fully parsed pair of FEC files for one cycle."""

    __tablename__ = "campaign_money_coverage"

    finance_cycle: Mapped[int] = mapped_column(Integer, primary_key=True)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    linkage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    summary_last_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linkage_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    linkage_last_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("complete IS TRUE", name="ck_campaign_money_complete"),
        CheckConstraint("candidate_count > 0", name="ck_campaign_money_candidates"),
        CheckConstraint("linkage_count > 0", name="ck_campaign_money_linkages"),
    )
