"""Bind cached bill text to the bill detail revision used to fetch it.

Revision ID: 0016
Revises: 0015

Existing text is preserved but has unknown provenance and is refreshed lazily.
No upstream calls or bulk text rewrite occurs during migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bill_text",
        sa.Column("bill_revision_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bill_text", "bill_revision_at")
