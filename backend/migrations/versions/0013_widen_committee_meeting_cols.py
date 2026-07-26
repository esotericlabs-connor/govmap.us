"""widen committee_meetings varchar columns

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-26

Congress.gov occasionally returns a `type`/`meetingStatus` (and, rarely, an
`eventId`) longer than the original VARCHAR(20), which raised
StringDataRightTruncationError and — because the load is a full replace in one
transaction — dropped *every* meeting for that run. Widen the offending columns
so a single long value can't abort the batch. event_id is part of the primary
key so it can only be widened (never truncated); meeting_type/status are short
categorical labels widened to a comfortable ceiling.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "committee_meetings",
        "event_id",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.alter_column(
        "committee_meetings",
        "meeting_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=True,
    )
    op.alter_column(
        "committee_meetings",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "committee_meetings",
        "status",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
    op.alter_column(
        "committee_meetings",
        "meeting_type",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
    op.alter_column(
        "committee_meetings",
        "event_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
