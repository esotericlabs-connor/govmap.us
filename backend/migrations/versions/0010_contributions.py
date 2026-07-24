"""contributions + donation_fetch: on-demand itemized donations ledger

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-24

Backs the per-member donations ledger (Increment 4b). `contributions` caches
individual FEC Schedule A receipts (disclosed contributions ≥ $200) pulled on
demand as visitors browse a member's ledger — the full corpus (200k+ per big
committee) is too large to mirror, so rows are fetched + cached lazily, keyed by
the FEC transaction sub_id. `donation_fetch` holds the keyset cursor + progress
per (member, cycle) so paging resumes where it left off. Populated at request
time by app/services/donations.py (requires FEC_API_KEY; fail-soft without it).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contributions",
        sa.Column("sub_id", sa.String(length=32), primary_key=True),
        sa.Column("bioguide_id", sa.String(length=7), nullable=False),
        sa.Column("committee_id", sa.String(length=20), nullable=False),
        sa.Column("cycle", sa.Integer(), nullable=False),
        sa.Column("contributor_name", sa.String(length=200), nullable=True),
        sa.Column("employer", sa.String(length=200), nullable=True),
        sa.Column("occupation", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=2), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("receipt_date", sa.Date(), nullable=True),
        sa.Column("aggregate_ytd", sa.Float(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_contributions_bioguide_id", "contributions", ["bioguide_id"])
    op.create_index(
        "ix_contrib_member_cycle_amount",
        "contributions",
        ["bioguide_id", "cycle", "amount"],
    )

    op.create_table(
        "donation_fetch",
        sa.Column("bioguide_id", sa.String(length=7), primary_key=True),
        sa.Column("cycle", sa.Integer(), primary_key=True),
        sa.Column("committee_id", sa.String(length=20), nullable=True),
        sa.Column("resolved", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=True),
        sa.Column("fetched_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cursor_amount", sa.String(length=40), nullable=True),
        sa.Column("cursor_index", sa.String(length=40), nullable=True),
        sa.Column("complete", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("donation_fetch")
    op.drop_index("ix_contrib_member_cycle_amount", table_name="contributions")
    op.drop_index("ix_contributions_bioguide_id", table_name="contributions")
    op.drop_table("contributions")
