from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Member(Base):
    """Federal legislator, keyed on Bioguide ID per AGENTS.md's normalization rules."""

    __tablename__ = "members"

    bioguide_id: Mapped[str] = mapped_column(String(7), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    official_full_name: Mapped[str] = mapped_column(String(200))
    chamber: Mapped[str] = mapped_column(String(6), index=True)  # "house" | "senate"
    state: Mapped[str] = mapped_column(String(2), index=True)
    district: Mapped[int | None] = mapped_column(nullable=True)
    party: Mapped[str] = mapped_column(String(30), index=True)
    # Start of the member's CURRENT term only — the same Jan-of-an-odd-year for
    # everyone re-elected (e.g. 2025-01-03 for the 119th), so NOT "in office
    # since". Kept because "current term began" is still a real fact.
    term_start: Mapped[date] = mapped_column(Date)
    # The real "in office since": start of the member's continuous service in
    # their current chamber, computed in the normalizer by walking back through
    # contiguous same-chamber terms (Cantwell → 2001, not 2025).
    served_since: Mapped[date | None] = mapped_column(Date, nullable=True)
    fec_candidate_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Enrichment from legislators-current.yaml (bio block + latest term contact).
    # social is JSONB and stays null until the social-media pipeline lands.
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(1), nullable=True)
    contact: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    social: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # False once the member leaves legislators-current.yaml (set by the roster
    # load, which guards against mass departures). Former members keep their
    # profile, votes, and bills; current-roster views filter on this.
    in_office: Mapped[bool] = mapped_column(Boolean, server_default="true")
    leadership_role: Mapped[str | None] = mapped_column(String(60), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MemberTerm(Base):
    """One congressional term of a member, from congress-legislators. Upserted
    on (bioguide_id, chamber, start_date) for members on the current roster;
    a departed member's terms stay as history."""

    __tablename__ = "member_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bioguide_id: Mapped[str] = mapped_column(
        String(7), ForeignKey("members.bioguide_id", ondelete="CASCADE")
    )
    chamber: Mapped[str] = mapped_column(String(6))
    state: Mapped[str] = mapped_column(String(2))
    district: Mapped[int | None] = mapped_column(Integer, nullable=True)
    party: Mapped[str | None] = mapped_column(String(60), nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    source_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("source_runs.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "bioguide_id", "chamber", "start_date", name="uq_member_terms_member_chamber_start"
        ),
        Index("ix_member_terms_source_run_id", "source_run_id"),
    )
