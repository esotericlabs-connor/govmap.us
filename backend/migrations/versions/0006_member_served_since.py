"""members.served_since: accurate "in office since" date

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-23

`term_start` only holds the CURRENT term's start (Jan-of-an-odd-year for anyone
re-elected — e.g. 2025 for the 119th), which made the member page show a wrong
"in office since". This adds `served_since` = the start of the member's
continuous service in their current chamber (computed in the normalizer).
Nullable + backfilled on the next members refresh.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("members", sa.Column("served_since", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("members", "served_since")
