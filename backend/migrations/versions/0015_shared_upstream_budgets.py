"""Persist rolling request budgets across processes and redeploys.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-11

The source rows serialize admission and start a one-time one-hour hold, since
the old processes' in-memory usage cannot be reconstructed. Stop old API and
worker containers before this first migration. No government data is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    budgets = op.create_table(
        "upstream_budgets",
        sa.Column("source", sa.String(length=16), primary_key=True),
        sa.Column(
            "initialized_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('congress', 'fec', 'govinfo')", name="ck_upstream_budgets_source"
        ),
    )
    op.bulk_insert(budgets, [{"source": source} for source in ("congress", "fec", "govinfo")])
    op.create_table(
        "upstream_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source"], ["upstream_budgets.source"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "scope IN ('shared', 'api', 'worker')", name="ck_upstream_requests_scope"
        ),
    )
    op.create_index(
        "ix_upstream_requests_source_started_at", "upstream_requests", ["source", "started_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_upstream_requests_source_started_at", table_name="upstream_requests")
    op.drop_table("upstream_requests")
    op.drop_table("upstream_budgets")
