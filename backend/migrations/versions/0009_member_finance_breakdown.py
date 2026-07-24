"""member_finance: full Form 3 receipts breakdown

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-24

Widens member_finance from the impoverished /candidates/totals aggregate (which
only exposed itemized-individual + PAC money) to the full /candidate/{id}/totals
Form 3 line items: the combined individual total, the itemized-vs-unitemized
(large-vs-small-dollar) split, party money, transfers, self-funding, loans,
other receipts, operating expenditures, and individual refunds. Existing columns
(receipts/disbursements/cash_on_hand/debts/individual_contributions/
pac_contributions/party_contributions) are unchanged; these are additive.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_COLUMNS = (
    "contributions",
    "individual_itemized",
    "individual_unitemized",
    "transfers",
    "candidate_contribution",
    "other_receipts",
    "loans",
    "operating_expenditures",
    "refunded_individual",
)


def upgrade() -> None:
    for name in _NEW_COLUMNS:
        op.add_column("member_finance", sa.Column(name, sa.Float(), nullable=True))


def downgrade() -> None:
    for name in reversed(_NEW_COLUMNS):
        op.drop_column("member_finance", name)
