"""bills.enriched_at + bill_text: on-demand bill enrichment & in-app full text

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-24

`bills.enriched_at` distinguishes fully-enriched bills (actions + cosponsors +
CRS summary + text link) from the ~17k "index" stubs the sponsored-legislation
pipeline creates (title + sponsor only). It's set by the congress_gov_bills
pull, by the on-demand enrichment on first view, and by the rolling backfill;
indexed so the backfill can cheaply find the next NULL rows. `bill_text` caches
the full legislative text (reduced to plain text) for in-platform rendering,
fetched lazily from GPO/govinfo on first view. Both are populated at request
time by app/services/bill_enrich.py.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_bills_enriched_at", "bills", ["enriched_at"])

    op.create_table(
        "bill_text",
        sa.Column("bill_id", sa.String(length=20), primary_key=True),
        sa.Column("text_version", sa.String(length=80), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("plain", sa.Text(), nullable=True),
        sa.Column("truncated", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.bill_id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("bill_text")
    op.drop_index("ix_bills_enriched_at", table_name="bills")
    op.drop_column("bills", "enriched_at")
