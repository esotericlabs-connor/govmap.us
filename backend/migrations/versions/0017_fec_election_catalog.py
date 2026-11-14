"""Store complete OpenFEC candidate and election-calendar snapshots.

Revision ID: 0017
Revises: 0016
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "election_candidates",
        sa.Column("finance_cycle", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.String(length=20), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("office", sa.String(length=1), nullable=True),
        sa.Column("office_full", sa.String(length=20), nullable=True),
        sa.Column("state", sa.String(length=2), nullable=True),
        sa.Column("district", sa.String(length=2), nullable=True),
        sa.Column("party", sa.String(length=3), nullable=True),
        sa.Column("party_full", sa.String(length=255), nullable=True),
        sa.Column("candidate_status", sa.String(length=1), nullable=True),
        sa.Column("incumbent_challenge", sa.String(length=1), nullable=True),
        sa.Column("first_file_date", sa.Date(), nullable=True),
        sa.Column("last_file_date", sa.Date(), nullable=True),
        sa.Column("cycles", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("election_years", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("principal_committees", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "office IS NULL OR office IN ('H', 'S', 'P')",
            name="ck_election_candidates_office",
        ),
    )
    op.create_table(
        "election_catalog_coverage",
        sa.Column("finance_cycle", sa.Integer(), primary_key=True),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("expected_count", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("snapshot_revision", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("complete IS TRUE", name="ck_election_catalog_complete"),
        sa.CheckConstraint("candidate_count > 0", name="ck_election_catalog_nonempty"),
        sa.CheckConstraint("page_count > 0", name="ck_election_catalog_pages"),
    )
    op.create_table(
        "election_calendar_events",
        sa.Column("calendar_year", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("state", postgresql.ARRAY(sa.String(length=100)), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.CheckConstraint("event_id > 0", name="ck_election_calendar_event_id"),
        sa.CheckConstraint(
            "category = 'Election Dates'",
            name="ck_election_calendar_category",
        ),
    )
    op.create_table(
        "election_calendar_coverage",
        sa.Column("calendar_year", sa.Integer(), primary_key=True),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("expected_count", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("snapshot_revision", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("complete IS TRUE", name="ck_election_calendar_complete"),
        sa.CheckConstraint("event_count > 0", name="ck_election_calendar_nonempty"),
        sa.CheckConstraint(
            "event_count = expected_count",
            name="ck_election_calendar_count_matches",
        ),
        sa.CheckConstraint("page_count > 0", name="ck_election_calendar_pages"),
    )


def downgrade() -> None:
    op.drop_table("election_calendar_coverage")
    op.drop_table("election_calendar_events")
    op.drop_table("election_catalog_coverage")
    op.drop_table("election_candidates")
