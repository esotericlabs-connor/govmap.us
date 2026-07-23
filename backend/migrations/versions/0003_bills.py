"""bills: bills, bill_actions, cosponsors (Increment 3a — Congress.gov)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-22

Second slice of the Legislative schema: current-Congress bills with their
sponsor, action timeline, and cosponsors, pulled from the Congress.gov v3 API.
sponsor/cosponsor bioguide columns are indexed but intentionally NOT foreign
keys — a bill's actors can include members no longer in the current-only
`members` table (see app/models/bill.py). Votes land in 0004.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- bills ---
    op.create_table(
        "bills",
        sa.Column("bill_id", sa.String(length=20), primary_key=True),
        sa.Column("congress", sa.Integer(), nullable=False),
        sa.Column("bill_type", sa.String(length=8), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("sponsor_bioguide_id", sa.String(length=7), nullable=True),
        sa.Column("introduced_date", sa.Date(), nullable=True),
        sa.Column("latest_action", sa.Text(), nullable=True),
        sa.Column("latest_action_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("policy_area", sa.String(length=120), nullable=True),
        sa.Column("summary_plain_english", sa.Text(), nullable=True),
        sa.Column("update_date", sa.Date(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_bills_congress", "bills", ["congress"])
    op.create_index("ix_bills_sponsor_bioguide_id", "bills", ["sponsor_bioguide_id"])
    op.create_index("ix_bills_update_date", "bills", ["update_date"])

    # --- bill_actions ---
    op.create_table(
        "bill_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "bill_id",
            sa.String(length=20),
            sa.ForeignKey("bills.bill_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("action_date", sa.Date(), nullable=True),
        sa.Column("chamber", sa.String(length=20), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_bill_actions_bill_id", "bill_actions", ["bill_id"])

    # --- cosponsors ---
    op.create_table(
        "cosponsors",
        sa.Column(
            "bill_id",
            sa.String(length=20),
            sa.ForeignKey("bills.bill_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("bioguide_id", sa.String(length=7), primary_key=True),
        sa.Column("sponsorship_date", sa.Date(), nullable=True),
        sa.Column("is_original", sa.Boolean(), nullable=True),
    )
    op.create_index("ix_cosponsors_bioguide_id", "cosponsors", ["bioguide_id"])


def downgrade() -> None:
    op.drop_index("ix_cosponsors_bioguide_id", table_name="cosponsors")
    op.drop_table("cosponsors")
    op.drop_index("ix_bill_actions_bill_id", table_name="bill_actions")
    op.drop_table("bill_actions")
    op.drop_index("ix_bills_update_date", table_name="bills")
    op.drop_index("ix_bills_sponsor_bioguide_id", table_name="bills")
    op.drop_index("ix_bills_congress", table_name="bills")
    op.drop_table("bills")
