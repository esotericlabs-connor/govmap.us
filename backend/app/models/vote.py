from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Vote(Base):
    """A roll-call vote. vote_id is `{h|s}{congress}-{session}-{roll}`, e.g.
    'h119-2-5' (House) or 's119-2-1' (Senate). Source: House Clerk EVS XML /
    Senate LIS XML."""

    __tablename__ = "votes"

    vote_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    chamber: Mapped[str] = mapped_column(String(6), index=True)  # house | senate
    congress: Mapped[int] = mapped_column(Integer, index=True)
    session: Mapped[int] = mapped_column(Integer)
    roll_number: Mapped[int] = mapped_column(Integer)
    date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Linked measure, best-effort (e.g. 'hr1234-119'); indexed, NOT an FK — the
    # bill may not be among the loaded set, but the reference is still useful.
    bill_id: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    totals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(300), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VotePosition(Base):
    """How one member voted on one roll call. bioguide_id is indexed but NOT an
    FK — an actor may have left the current-members table, and Senate positions
    are resolved from the LIS member id via id_crosswalk (the crosswalk's first
    real payoff). Positions are re-fetched whole and replaced per refreshed
    vote."""

    __tablename__ = "vote_positions"

    vote_id: Mapped[str] = mapped_column(
        String(24), ForeignKey("votes.vote_id", ondelete="CASCADE"), primary_key=True
    )
    bioguide_id: Mapped[str] = mapped_column(String(7), primary_key=True)
    position: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Yea/Nay/Present/Not Voting/Aye/No
