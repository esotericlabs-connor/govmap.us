"""source_runs + member_terms: per-run history and office-term records

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-11

source_runs keeps one row per refresh attempt (pipeline_status only keeps the
latest), so a degraded or skipped run stays visible after the next one, and
records which staging inputs a load used. member_terms records each legislator
term from congress-legislators, so a member's service history survives their
departure from the current roster. Additive only: nothing existing is altered.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("code_version", sa.String(length=40), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("items_total", sa.Integer(), nullable=True),
        sa.Column("items_succeeded", sa.Integer(), nullable=True),
        sa.Column("items_failed", sa.Integer(), nullable=True),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "outcome IN ('running', 'ok', 'partial', 'error', 'skipped', 'abandoned')",
            name="ck_source_runs_outcome",
        ),
    )
    op.create_index(
        "ix_source_runs_source_started_at", "source_runs", ["source", "started_at"]
    )

    op.create_table(
        "member_terms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bioguide_id", sa.String(length=7), nullable=False),
        sa.Column("chamber", sa.String(length=6), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("district", sa.Integer(), nullable=True),
        sa.Column("party", sa.String(length=60), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("source_run_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["bioguide_id"], ["members.bioguide_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_run_id"], ["source_runs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "bioguide_id", "chamber", "start_date", name="uq_member_terms_member_chamber_start"
        ),
    )
    op.create_index("ix_member_terms_source_run_id", "member_terms", ["source_run_id"])


def downgrade() -> None:
    op.drop_index("ix_member_terms_source_run_id", table_name="member_terms")
    op.drop_table("member_terms")
    op.drop_index("ix_source_runs_source_started_at", table_name="source_runs")
    op.drop_table("source_runs")
