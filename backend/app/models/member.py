from datetime import date, datetime

from sqlalchemy import ARRAY, Boolean, Date, DateTime, String, func
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
    in_office: Mapped[bool] = mapped_column(Boolean, server_default="true")
    leadership_role: Mapped[str | None] = mapped_column(String(60), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
