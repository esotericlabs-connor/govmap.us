"""member_finance: FEC campaign-finance totals per member per cycle

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-23

Backs the member page's Campaign Finance section (Increment 4). One row per
(member, election cycle): receipts / disbursements / cash-on-hand / debts and
the individual-vs-PAC-vs-party contribution split, from OpenFEC. Populated by
app/pipelines/fec_finance.py (requires FEC_API_KEY; fail-soft without it).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "member_finance",
        sa.Column("bioguide_id", sa.String(length=7), primary_key=True),
        sa.Column("cycle", sa.Integer(), primary_key=True),
        sa.Column("fec_candidate_id", sa.String(length=20), nullable=False),
        sa.Column("receipts", sa.Float(), nullable=True),
        sa.Column("disbursements", sa.Float(), nullable=True),
        sa.Column("cash_on_hand", sa.Float(), nullable=True),
        sa.Column("debts", sa.Float(), nullable=True),
        sa.Column("individual_contributions", sa.Float(), nullable=True),
        sa.Column("pac_contributions", sa.Float(), nullable=True),
        sa.Column("party_contributions", sa.Float(), nullable=True),
        sa.Column("coverage_start", sa.Date(), nullable=True),
        sa.Column("coverage_end", sa.Date(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("member_finance")
