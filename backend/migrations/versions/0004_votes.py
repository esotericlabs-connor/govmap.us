"""votes: votes, vote_positions (Increment 3b — House Clerk + Senate LIS)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-23

Roll-call votes and per-member positions. House positions key on Bioguide ID
directly (Clerk EVS `name-id`); Senate positions are resolved from the LIS
member id via id_crosswalk in the normalizer. bioguide_id is indexed but not a
foreign key (see app/models/vote.py).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "votes",
        sa.Column("vote_id", sa.String(length=24), primary_key=True),
        sa.Column("chamber", sa.String(length=6), nullable=False),
        sa.Column("congress", sa.Integer(), nullable=False),
        sa.Column("session", sa.Integer(), nullable=False),
        sa.Column("roll_number", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("result", sa.String(length=120), nullable=True),
        sa.Column("bill_id", sa.String(length=20), nullable=True),
        sa.Column("totals", postgresql.JSONB(), nullable=True),
        sa.Column("source_url", sa.String(length=300), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_votes_chamber", "votes", ["chamber"])
    op.create_index("ix_votes_congress", "votes", ["congress"])
    op.create_index("ix_votes_date", "votes", ["date"])
    op.create_index("ix_votes_bill_id", "votes", ["bill_id"])

    op.create_table(
        "vote_positions",
        sa.Column(
            "vote_id",
            sa.String(length=24),
            sa.ForeignKey("votes.vote_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("bioguide_id", sa.String(length=7), primary_key=True),
        sa.Column("position", sa.String(length=20), nullable=True),
    )
    op.create_index("ix_vote_positions_bioguide", "vote_positions", ["bioguide_id"])


def downgrade() -> None:
    op.drop_index("ix_vote_positions_bioguide", table_name="vote_positions")
    op.drop_table("vote_positions")
    op.drop_index("ix_votes_bill_id", table_name="votes")
    op.drop_index("ix_votes_date", table_name="votes")
    op.drop_index("ix_votes_congress", table_name="votes")
    op.drop_index("ix_votes_chamber", table_name="votes")
    op.drop_table("votes")
