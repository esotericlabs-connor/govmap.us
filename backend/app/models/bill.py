from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Bill(Base):
    """A bill or resolution in the current Congress. Source: Congress.gov v3.

    bill_id is the canonical key `{type}{number}-{congress}`, e.g. "hr3076-117".
    """

    __tablename__ = "bills"

    bill_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    congress: Mapped[int] = mapped_column(Integer, index=True)
    bill_type: Mapped[str] = mapped_column(String(8))  # hr, s, hres, sjres, ...
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sponsor is a plain indexed column, NOT a foreign key: a current-Congress
    # bill can be sponsored by a member who has since left, while `members`
    # holds only current members. bioguide_id remains the logical join key
    # (AGENTS.md) — we simply don't enforce referential integrity across that
    # current-only boundary (same reasoning for cosponsors.bioguide_id).
    sponsor_bioguide_id: Mapped[str | None] = mapped_column(String(7), index=True, nullable=True)

    introduced_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    latest_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_action_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Coarse, factual status — only the unambiguous "Became Law" is derived
    # (from the presence of `laws`); the full truth lives in bill_actions. No
    # invented status taxonomy (data-only, no editorializing — AGENTS.md).
    status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    policy_area: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Reserved for the (on-hold) plain-English summary work — stays null.
    summary_plain_english: Mapped[str | None] = mapped_column(Text, nullable=True)
    update_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BillAction(Base):
    """One entry in a bill's legislative-history timeline. Fully re-fetched and
    replaced per bill on each refresh, so `seq` (position in the source list) is
    a stable enough ordering key without a natural per-action ID."""

    __tablename__ = "bill_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bill_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("bills.bill_id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    action_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    chamber: Mapped[str | None] = mapped_column(String(20), nullable=True)  # House/Senate/Library of Congress
    text: Mapped[str] = mapped_column(Text)
    action_type: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Cosponsor(Base):
    """A member's cosponsorship of a bill. bioguide_id is indexed but not an FK
    (see Bill.sponsor_bioguide_id)."""

    __tablename__ = "cosponsors"

    bill_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("bills.bill_id", ondelete="CASCADE"), primary_key=True
    )
    bioguide_id: Mapped[str] = mapped_column(String(7), primary_key=True)
    sponsorship_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_original: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
