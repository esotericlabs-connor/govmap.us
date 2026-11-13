from datetime import date, datetime

from sqlalchemy import ARRAY, Boolean, CheckConstraint, Date, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ElectionCandidate(Base):
    """OpenFEC candidate record scoped to a finance cycle.

    FEC candidate IDs are publisher-native identities, not Bioguide IDs.
    Election years and finance cycles are stored separately because a Senate
    candidate's reporting cycles do not identify a single election year.
    """

    __tablename__ = "election_candidates"

    finance_cycle: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    office: Mapped[str | None] = mapped_column(String(1), nullable=True)
    office_full: Mapped[str | None] = mapped_column(String(20), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    district: Mapped[str | None] = mapped_column(String(2), nullable=True)
    party: Mapped[str | None] = mapped_column(String(3), nullable=True)
    party_full: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_status: Mapped[str | None] = mapped_column(String(1), nullable=True)
    incumbent_challenge: Mapped[str | None] = mapped_column(String(1), nullable=True)
    first_file_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_file_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cycles: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, default=list)
    election_years: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, default=list)
    principal_committees: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    __table_args__ = (
        CheckConstraint(
            "office IS NULL OR office IN ('H', 'S', 'P')",
            name="ck_election_candidates_office",
        ),
    )


class ElectionCatalogCoverage(Base):
    """Last fully loaded OpenFEC candidate snapshot for each finance cycle."""

    __tablename__ = "election_catalog_coverage"

    finance_cycle: Mapped[int] = mapped_column(Integer, primary_key=True)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("complete IS TRUE", name="ck_election_catalog_complete"),
        CheckConstraint("candidate_count > 0", name="ck_election_catalog_nonempty"),
        CheckConstraint("page_count > 0", name="ck_election_catalog_pages"),
    )


class ElectionCalendarEvent(Base):
    """FEC-published election-date event; not evidence of ballot access or results."""

    __tablename__ = "election_calendar_events"

    calendar_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("event_id > 0", name="ck_election_calendar_event_id"),
        CheckConstraint(
            "category = 'Election Dates'",
            name="ck_election_calendar_category",
        ),
    )


class ElectionCalendarCoverage(Base):
    """Last fully loaded OpenFEC Election Dates snapshot for each calendar year."""

    __tablename__ = "election_calendar_coverage"

    calendar_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("complete IS TRUE", name="ck_election_calendar_complete"),
        CheckConstraint("event_count > 0", name="ck_election_calendar_nonempty"),
        CheckConstraint(
            "event_count = expected_count",
            name="ck_election_calendar_count_matches",
        ),
        CheckConstraint("page_count > 0", name="ck_election_calendar_pages"),
    )
