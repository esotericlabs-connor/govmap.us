from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MemberFinance(Base):
    """Campaign-finance totals for a member's current-office FEC candidate, per
    two-year election cycle. Source: OpenFEC ``/candidate/{id}/totals``.

    Amounts are display aggregates in USD, already rounded to cents by the FEC —
    stored as Float (double precision represents cent values well past any real
    campaign total exactly). One row per (member, cycle); the current-office
    candidate id is chosen by chamber prefix (S… for senators, H… for
    representatives).
    """

    __tablename__ = "member_finance"

    bioguide_id: Mapped[str] = mapped_column(String(7), primary_key=True)
    cycle: Mapped[int] = mapped_column(Integer, primary_key=True)
    fec_candidate_id: Mapped[str] = mapped_column(String(20))

    receipts: Mapped[float | None] = mapped_column(Float, nullable=True)
    disbursements: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_on_hand: Mapped[float | None] = mapped_column(Float, nullable=True)
    debts: Mapped[float | None] = mapped_column(Float, nullable=True)
    individual_contributions: Mapped[float | None] = mapped_column(Float, nullable=True)
    pac_contributions: Mapped[float | None] = mapped_column(Float, nullable=True)
    party_contributions: Mapped[float | None] = mapped_column(Float, nullable=True)

    coverage_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    coverage_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
