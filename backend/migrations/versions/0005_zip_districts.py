"""zip_districts: ZIP→congressional-district crosswalk (map + reps lookup)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-22

Backs GET /api/lookup ("find your representatives"). One ZIP can map to
multiple (state, district) rows, so the primary key is the composite
(zip, state, district). Populated from the public Census ZCTA→CD relationship
file by app/pipelines/zip_crosswalk.py (no auth, self-contained).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zip_districts",
        sa.Column("zip", sa.String(length=5), primary_key=True),
        sa.Column("state", sa.String(length=2), primary_key=True),
        sa.Column("district", sa.Integer(), primary_key=True),
    )
    # The PK's leading column already indexes `zip` for the lookup query; a
    # (state, district) index accelerates the reverse join to House members.
    op.create_index(
        "ix_zip_districts_state_district", "zip_districts", ["state", "district"]
    )


def downgrade() -> None:
    op.drop_index("ix_zip_districts_state_district", table_name="zip_districts")
    op.drop_table("zip_districts")
