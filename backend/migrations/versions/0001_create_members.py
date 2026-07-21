"""create members table

Revision ID: 0001
Revises:
Create Date: 2026-07-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "members",
        sa.Column("bioguide_id", sa.String(length=7), primary_key=True),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("official_full_name", sa.String(length=200), nullable=False),
        sa.Column("chamber", sa.String(length=6), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("district", sa.Integer(), nullable=True),
        sa.Column("party", sa.String(length=30), nullable=False),
        sa.Column("term_start", sa.Date(), nullable=False),
        sa.Column(
            "fec_candidate_ids",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("photo_url", sa.String(length=500), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_members_chamber", "members", ["chamber"])
    op.create_index("ix_members_state", "members", ["state"])
    op.create_index("ix_members_party", "members", ["party"])


def downgrade() -> None:
    op.drop_index("ix_members_party", table_name="members")
    op.drop_index("ix_members_state", table_name="members")
    op.drop_index("ix_members_chamber", table_name="members")
    op.drop_table("members")
