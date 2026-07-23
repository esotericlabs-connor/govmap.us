from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Committee(Base):
    """Congressional committee or subcommittee. Subcommittees point at their
    parent via parent_committee_id. Source: unitedstates/congress-legislators
    committees-current.yaml."""

    __tablename__ = "committees"

    committee_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    thomas_id: Mapped[str | None] = mapped_column(String(10), nullable=True)
    name: Mapped[str] = mapped_column(String(300))
    chamber: Mapped[str] = mapped_column(String(10), index=True)  # house | senate | joint
    committee_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    parent_committee_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("committees.committee_id"), nullable=True
    )
    url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CommitteeMembership(Base):
    """A member's seat on a committee/subcommittee. Source:
    committee-membership-current.yaml."""

    __tablename__ = "committee_memberships"

    committee_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("committees.committee_id", ondelete="CASCADE"), primary_key=True
    )
    bioguide_id: Mapped[str] = mapped_column(
        String(7), ForeignKey("members.bioguide_id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str | None] = mapped_column(String(30), nullable=True)  # Chair / Ranking / Member
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    side: Mapped[str | None] = mapped_column(String(10), nullable=True)  # majority / minority
