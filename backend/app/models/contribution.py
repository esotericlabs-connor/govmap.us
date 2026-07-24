from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Contribution(Base):
    """One itemized FEC Schedule A receipt to a member's principal campaign
    committee — a disclosed contribution (individuals aggregating ≥ $200, plus
    PAC/party/committee transfers). Cached on demand as visitors browse a
    member's donations ledger (the corpus is far too large to mirror in bulk —
    a single big committee reports 200k+ receipts per cycle).

    Keyed by the FEC transaction ``sub_id`` so re-fetches dedupe idempotently.
    Small-dollar (< $200) individual gifts are never itemized by the FEC and so
    never appear here — only their lump sum shows, on member_finance.
    """

    __tablename__ = "contributions"

    sub_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    bioguide_id: Mapped[str] = mapped_column(String(7), index=True)
    committee_id: Mapped[str] = mapped_column(String(20))
    cycle: Mapped[int] = mapped_column(Integer)

    contributor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    aggregate_ytd: Mapped[float | None] = mapped_column(Float, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        # The ledger is served ORDER BY amount DESC over a (member, cycle) slice.
        Index("ix_contrib_member_cycle_amount", "bioguide_id", "cycle", "amount"),
    )


class DonationFetch(Base):
    """Cursor + progress bookkeeping for a member's on-demand donations cache,
    one row per (bioguide_id, cycle). Records the resolved principal committee,
    the FEC keyset cursor to resume from, how many receipts we've cached, the
    FEC-reported grand total, and whether the whole ledger has been pulled.
    """

    __tablename__ = "donation_fetch"

    bioguide_id: Mapped[str] = mapped_column(String(7), primary_key=True)
    cycle: Mapped[int] = mapped_column(Integer, primary_key=True)
    committee_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # True once committee resolution has run, even if it found no committee — so
    # a member who has never had a campaign committee isn't re-resolved forever.
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    total_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    # FEC keyset cursor (strings, as the API returns them) to resume paging.
    cursor_amount: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cursor_index: Mapped[str | None] = mapped_column(String(40), nullable=True)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
