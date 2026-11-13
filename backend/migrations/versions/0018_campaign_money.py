"""Store exact FEC candidate finance summaries and committee linkages.

Revision ID: 0018
Revises: 0017
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_finance_summaries",
        sa.Column("finance_cycle", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.String(length=9), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("office", sa.String(length=1), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=True),
        sa.Column("district", sa.String(length=2), nullable=True),
        sa.Column("party", sa.String(length=3), nullable=True),
        sa.Column("incumbent_challenge", sa.String(length=1), nullable=True),
        sa.Column("receipts", sa.Numeric(14, 2), nullable=True),
        sa.Column("transfers_from_authorized", sa.Numeric(14, 2), nullable=True),
        sa.Column("disbursements", sa.Numeric(14, 2), nullable=True),
        sa.Column("transfers_to_authorized", sa.Numeric(14, 2), nullable=True),
        sa.Column("cash_beginning", sa.Numeric(14, 2), nullable=True),
        sa.Column("cash_on_hand", sa.Numeric(14, 2), nullable=True),
        sa.Column("candidate_contributions", sa.Numeric(14, 2), nullable=True),
        sa.Column("candidate_loans", sa.Numeric(14, 2), nullable=True),
        sa.Column("other_loans", sa.Numeric(14, 2), nullable=True),
        sa.Column("candidate_loan_repayments", sa.Numeric(14, 2), nullable=True),
        sa.Column("other_loan_repayments", sa.Numeric(14, 2), nullable=True),
        sa.Column("debts", sa.Numeric(14, 2), nullable=True),
        sa.Column("individual_contributions", sa.Numeric(14, 2), nullable=True),
        sa.Column("other_committee_contributions", sa.Numeric(14, 2), nullable=True),
        sa.Column("party_contributions", sa.Numeric(14, 2), nullable=True),
        sa.Column("individual_refunds", sa.Numeric(14, 2), nullable=True),
        sa.Column("committee_refunds", sa.Numeric(14, 2), nullable=True),
        sa.Column("coverage_end", sa.Date(), nullable=True),
        sa.CheckConstraint("office IN ('H', 'S', 'P')", name="ck_candidate_finance_office"),
    )
    op.create_index(
        "ix_candidate_finance_filters",
        "candidate_finance_summaries",
        ["finance_cycle", "office", "state", "district", "coverage_end"],
    )
    op.create_table(
        "candidate_committee_links",
        sa.Column("finance_cycle", sa.Integer(), primary_key=True),
        sa.Column("linkage_id", sa.BigInteger(), primary_key=True),
        sa.Column("subject_id", sa.String(length=9), nullable=False),
        sa.Column("candidate_election_year", sa.Integer(), nullable=False),
        sa.Column("fec_election_year", sa.Integer(), nullable=False),
        sa.Column("committee_id", sa.String(length=9), nullable=True),
        sa.Column("committee_type", sa.String(length=1), nullable=True),
        sa.Column("designation", sa.String(length=1), nullable=True),
        sa.CheckConstraint(
            "fec_election_year = finance_cycle", name="ck_candidate_link_finance_cycle"
        ),
    )
    op.create_index(
        "ix_candidate_committee_links_subject",
        "candidate_committee_links",
        ["finance_cycle", "subject_id"],
    )
    op.create_table(
        "campaign_money_coverage",
        sa.Column("finance_cycle", sa.Integer(), primary_key=True),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("linkage_count", sa.Integer(), nullable=False),
        sa.Column("summary_sha256", sa.String(length=64), nullable=False),
        sa.Column("summary_last_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linkage_sha256", sa.String(length=64), nullable=False),
        sa.Column("linkage_last_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_revision", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("complete IS TRUE", name="ck_campaign_money_complete"),
        sa.CheckConstraint("candidate_count > 0", name="ck_campaign_money_candidates"),
        sa.CheckConstraint("linkage_count > 0", name="ck_campaign_money_linkages"),
    )


def downgrade() -> None:
    op.drop_table("campaign_money_coverage")
    op.drop_index("ix_candidate_committee_links_subject", table_name="candidate_committee_links")
    op.drop_table("candidate_committee_links")
    op.drop_index("ix_candidate_finance_filters", table_name="candidate_finance_summaries")
    op.drop_table("candidate_finance_summaries")
