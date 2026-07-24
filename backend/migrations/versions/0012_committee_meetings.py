"""committee_meetings: scheduled/held committee meetings (Congress.gov)

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-24

Backs the "upcoming meetings" + recent-activity sections on the committee page.
Rows come from the Congress.gov /committee-meeting endpoint via the
congress_committee_meetings pipeline (full-replace per run; meetings churn and
canceled ones drop). Keyed by (event_id, committee_id) so a meeting shared by a
full committee and a subcommittee shows under both.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "committee_meetings",
        sa.Column("event_id", sa.String(length=20), primary_key=True),
        sa.Column("committee_id", sa.String(length=20), primary_key=True),
        sa.Column("chamber", sa.String(length=10), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("meeting_type", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("meeting_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("bill_ids", sa.JSON(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["committee_id"], ["committees.committee_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_committee_meetings_committee_dt",
        "committee_meetings",
        ["committee_id", "meeting_datetime"],
    )


def downgrade() -> None:
    op.drop_index("ix_committee_meetings_committee_dt", table_name="committee_meetings")
    op.drop_table("committee_meetings")
