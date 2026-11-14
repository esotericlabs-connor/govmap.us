import asyncio
import os
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.bill import Bill
from app.models.committee import Committee, CommitteeMeeting
from app.models.member import Member
from app.models.pipeline_status import PipelineStatusRow
from app.models.vote import Vote
from app.routers.overview import build_overview, week_start
from app.sources import SOURCES

_needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
_TABLES = [
    Member.__table__,
    Vote.__table__,
    Bill.__table__,
    Committee.__table__,
    CommitteeMeeting.__table__,
    PipelineStatusRow.__table__,
]

# A Thursday, so the current week (from Monday 11-09) is partly elapsed.
_NOW = datetime(2026, 11, 12, 15, tzinfo=UTC)
_WEEKS = [date(2026, 10, 19), date(2026, 10, 26), date(2026, 11, 2), date(2026, 11, 9)]


def test_week_start_is_the_monday_of_the_week() -> None:
    assert week_start(date(2026, 11, 9)) == date(2026, 11, 9)
    assert week_start(date(2026, 11, 12)) == date(2026, 11, 9)
    assert week_start(date(2026, 11, 15)) == date(2026, 11, 9)
    assert week_start(date(2026, 11, 16)) == date(2026, 11, 16)


def _member(bioguide_id: str, chamber: str, party: str, *, in_office: bool = True) -> Member:
    return Member(
        bioguide_id=bioguide_id,
        first_name="Test",
        last_name=bioguide_id,
        official_full_name=f"Test {bioguide_id}",
        chamber=chamber,
        state="VA",
        party=party,
        term_start=date(2025, 1, 3),
        in_office=in_office,
    )


def _vote(vote_id: str, chamber: str, day: date | None) -> Vote:
    return Vote(vote_id=vote_id, chamber=chamber, congress=119, session=2, roll_number=1, date=day)


def _bill(number: int, congress: int = 119, **fields: Any) -> Bill:
    return Bill(
        bill_id=f"hr{number}-{congress}",
        congress=congress,
        bill_type="hr",
        number=number,
        **fields,
    )


def _meeting(event_id: str, committee_id: str, starts_at: datetime | None, **fields: Any) -> CommitteeMeeting:
    return CommitteeMeeting(
        event_id=event_id, committee_id=committee_id, meeting_datetime=starts_at, **fields
    )


@_needs_postgres
def test_overview_reports_balance_activity_meetings_and_freshness() -> None:
    async def run() -> None:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            # This database belongs exclusively to the CI job, not the app.
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: Base.metadata.create_all(sync, tables=_TABLES)
                )
            async with factory() as session:
                session.add_all(
                    [
                        _member("H000001", "house", "Democrat"),
                        _member("H000002", "house", "Republican"),
                        _member("H000003", "house", "Republican"),
                        _member("H000004", "house", "Democrat", in_office=False),
                        _member("S000001", "senate", "Democrat"),
                        _member("S000002", "senate", "Independent"),
                        # House: stored from 09-01, so every window week counts.
                        _vote("h-0901", "house", date(2026, 9, 1)),
                        _vote("h-1027a", "house", date(2026, 10, 27)),
                        _vote("h-1027b", "house", date(2026, 10, 27)),
                        _vote("h-1110", "house", date(2026, 11, 10)),
                        _vote("h-undated", "house", None),
                        # After "today": outside the window, not a KeyError.
                        _vote("h-1116", "house", date(2026, 11, 16)),
                        # Senate: first stored vote 11-04, so the two earlier
                        # weeks were never collected.
                        _vote("s-1104", "senate", date(2026, 11, 4)),
                        _bill(1, introduced_date=date(2026, 10, 20)),
                        _bill(2, introduced_date=date(2026, 10, 21), status="Became Law"),
                        _bill(3, introduced_date=date(2026, 11, 12)),
                        _bill(4, status="Became Law"),
                        _bill(5, introduced_date=date(2026, 1, 5)),
                        _bill(7, introduced_date=date(2026, 11, 20)),
                        # Previous Congress: excluded from every count.
                        _bill(6, congress=118, introduced_date=date(2026, 10, 20), status="Became Law"),
                        PipelineStatusRow(
                            source="votes",
                            last_success=datetime(2026, 11, 12, 6, tzinfo=UTC),
                            status="ok",
                            detail="internal detail",
                        ),
                        PipelineStatusRow(
                            source="not_a_registered_source",
                            last_success=datetime(2026, 11, 12, 6, tzinfo=UTC),
                            status="error",
                        ),
                    ]
                )
                session.add_all(
                    [
                        Committee(committee_id="HSAG", name="Committee on Agriculture", chamber="house"),
                        Committee(committee_id="SSFI", name="Committee on Finance", chamber="senate"),
                    ]
                )
                await session.flush()
                session.add(
                    Committee(
                        committee_id="HSAG15",
                        name="Subcommittee on Forestry",
                        chamber="house",
                        parent_committee_id="HSAG",
                    )
                )
                await session.flush()
                session.add_all(
                    [
                        _meeting("E0", "SSFI", datetime(2026, 11, 11, 15, tzinfo=UTC)),
                        _meeting("E-undated", "HSAG", None),
                        # Stored under the committee and its subcommittee.
                        *(
                            _meeting(
                                "E1",
                                committee_id,
                                datetime(2026, 11, 13, 14, tzinfo=UTC),
                                chamber="House",
                                title="Farm bill markup",
                                meeting_type="Markup",
                                status="Scheduled",
                            )
                            for committee_id in ("HSAG15", "HSAG")
                        ),
                        _meeting(
                            "E2",
                            "SSFI",
                            datetime(2026, 11, 12, 16, tzinfo=UTC),
                            status="Canceled",
                        ),
                        *(
                            _meeting(f"E1{i}", "SSFI", datetime(2026, 11, 16 + i, 14, tzinfo=UTC))
                            for i in range(5)
                        ),
                    ]
                )
                await session.commit()

            async with factory() as session:
                overview = await build_overview(session, weeks=4, now=_NOW, congress=119)

            assert overview.congress == 119
            assert overview.generated_at == _NOW
            assert overview.chambers.house.model_dump() == {"D": 1, "R": 2, "I": 0, "total": 3}
            assert overview.chambers.senate.model_dump() == {"D": 1, "R": 0, "I": 1, "total": 2}

            activity = overview.activity
            assert activity.weeks == _WEEKS
            assert activity.votes.house == [0, 2, 0, 1]
            assert activity.votes.senate == [None, None, 1, 0]
            assert activity.votes_covered_from.house == date(2026, 9, 1)
            assert activity.votes_covered_from.senate == date(2026, 11, 4)
            assert activity.bills_introduced == [2, 0, 0, 1]
            assert overview.bills_in_congress == 6
            assert overview.laws_enacted == 2

            meetings = overview.upcoming_meetings
            assert [(m.event_id, m.committee_id) for m in meetings] == [
                ("E2", "SSFI"),
                ("E1", "HSAG"),
                ("E10", "SSFI"),
                ("E11", "SSFI"),
                ("E12", "SSFI"),
                ("E13", "SSFI"),
            ]
            assert meetings[0].status == "Canceled"
            assert meetings[0].starts_at == datetime(2026, 11, 12, 16, tzinfo=UTC)
            assert meetings[1].committee_name == "Committee on Agriculture"
            assert meetings[1].title == "Farm bill markup"

            assert [s.name for s in overview.sources] == list(SOURCES)
            freshness = {s.name: s.last_success for s in overview.sources}
            assert freshness["votes"] == datetime(2026, 11, 12, 6, tzinfo=UTC)
            assert freshness["congress_gov_bills"] is None
            # Run status and error detail stay on the authenticated endpoints.
            assert set(overview.model_dump()["sources"][0]) == {
                "name",
                "title",
                "publisher",
                "last_success",
            }
        finally:
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: Base.metadata.drop_all(sync, tables=_TABLES)
                )
            await engine.dispose()

    asyncio.run(run())


@_needs_postgres
def test_overview_marks_every_week_uncollected_without_votes() -> None:
    async def run() -> None:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: Base.metadata.create_all(sync, tables=_TABLES)
                )
            async with factory() as session:
                overview = await build_overview(session, weeks=4, now=_NOW, congress=119)

            assert overview.activity.votes.house == [None] * 4
            assert overview.activity.votes.senate == [None] * 4
            assert overview.activity.votes_covered_from.house is None
            assert overview.activity.bills_introduced == [0] * 4
            assert overview.bills_in_congress == 0
            assert overview.laws_enacted == 0
            assert overview.upcoming_meetings == []
            assert overview.chambers.house.total == 0
            assert all(s.last_success is None for s in overview.sources)
        finally:
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: Base.metadata.drop_all(sync, tables=_TABLES)
                )
            await engine.dispose()

    asyncio.run(run())
