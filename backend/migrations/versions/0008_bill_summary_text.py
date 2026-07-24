"""bills: CRS summary + full-text link ("what this bill does")

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-24

Adds the official Congressional Research Service summary (plain text) and a link
to the latest full-text version to each bill. Populated by the enriched
congress_gov_bills pipeline (summaries + text sub-resources).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("bills", sa.Column("summary_date", sa.Date(), nullable=True))
    op.add_column("bills", sa.Column("text_url", sa.String(length=500), nullable=True))
    op.add_column("bills", sa.Column("text_version", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("bills", "text_version")
    op.drop_column("bills", "text_url")
    op.drop_column("bills", "summary_date")
    op.drop_column("bills", "summary")
