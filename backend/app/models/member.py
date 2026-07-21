from datetime import date, datetime

from sqlalchemy import ARRAY, Date, DateTime, String, func
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
    term_start: Mapped[date] = mapped_column(Date)
    fec_candidate_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
