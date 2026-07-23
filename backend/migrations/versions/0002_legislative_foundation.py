"""legislative foundation: member enrichment, id_crosswalk, committees, pipeline_status

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-22

First slice of the Legislative-branch schema (see the ERD in CODE-MANIFEST):
extends members, adds the id_crosswalk join backbone, committees +
memberships, and promotes pipeline_status from a JSON file to a table. Bills/
votes (0003) and finance/lobbying/disclosures (0004) land in later revisions.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- members enrichment ---
    op.add_column("members", sa.Column("birthday", sa.Date(), nullable=True))
    op.add_column("members", sa.Column("gender", sa.String(length=1), nullable=True))
    op.add_column("members", sa.Column("contact", postgresql.JSONB(), nullable=True))
    op.add_column("members", sa.Column("social", postgresql.JSONB(), nullable=True))
    op.add_column(
        "members",
        sa.Column("in_office", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column("members", sa.Column("leadership_role", sa.String(length=60), nullable=True))

    # --- id_crosswalk ---
    op.create_table(
        "id_crosswalk",
        sa.Column(
            "bioguide_id",
            sa.String(length=7),
            sa.ForeignKey("members.bioguide_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "fec_ids", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"
        ),
        sa.Column("govtrack", sa.Integer(), nullable=True),
        sa.Column("opensecrets", sa.String(length=20), nullable=True),
        sa.Column("thomas", sa.String(length=10), nullable=True),
        sa.Column("lis", sa.String(length=10), nullable=True),
        sa.Column("votesmart", sa.Integer(), nullable=True),
        sa.Column("wikidata", sa.String(length=20), nullable=True),
    )

    # --- committees (self-referential for subcommittees) ---
    op.create_table(
        "committees",
        sa.Column("committee_id", sa.String(length=20), primary_key=True),
        sa.Column("thomas_id", sa.String(length=10), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("chamber", sa.String(length=10), nullable=False),
        sa.Column("committee_type", sa.String(length=20), nullable=True),
        sa.Column(
            "parent_committee_id",
            sa.String(length=20),
            sa.ForeignKey("committees.committee_id"),
            nullable=True,
        ),
        sa.Column("url", sa.String(length=300), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_committees_chamber", "committees", ["chamber"])

    # --- committee_memberships ---
    op.create_table(
        "committee_memberships",
        sa.Column(
            "committee_id",
            sa.String(length=20),
            sa.ForeignKey("committees.committee_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "bioguide_id",
            sa.String(length=7),
            sa.ForeignKey("members.bioguide_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(length=30), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("side", sa.String(length=10), nullable=True),
    )
    op.create_index(
        "ix_committee_memberships_bioguide", "committee_memberships", ["bioguide_id"]
    )

    # --- pipeline_status (was a JSON file) ---
    op.create_table(
        "pipeline_status",
        sa.Column("source", sa.String(length=50), primary_key=True),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("pipeline_status")
    op.drop_index("ix_committee_memberships_bioguide", table_name="committee_memberships")
    op.drop_table("committee_memberships")
    op.drop_index("ix_committees_chamber", table_name="committees")
    op.drop_table("committees")
    op.drop_table("id_crosswalk")
    op.drop_column("members", "leadership_role")
    op.drop_column("members", "in_office")
    op.drop_column("members", "social")
    op.drop_column("members", "contact")
    op.drop_column("members", "gender")
    op.drop_column("members", "birthday")
