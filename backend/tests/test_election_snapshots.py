import asyncio
import os
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base
from app.models.election import (
    ElectionCalendarCoverage,
    ElectionCalendarEvent,
    ElectionCandidate,
    ElectionCatalogCoverage,
)
from app.routers.elections import list_election_calendar, list_election_candidates

_TABLES = [
    ElectionCalendarCoverage.__table__,
    ElectionCalendarEvent.__table__,
    ElectionCatalogCoverage.__table__,
    ElectionCandidate.__table__,
]


async def _replace_snapshot(
    factory: async_sessionmaker[AsyncSession], resource: str, count: int
) -> None:
    fetched_at = datetime(2026, 1, 1, tzinfo=UTC)
    async with factory.begin() as session:
        if resource == "calendar":
            await session.execute(delete(ElectionCalendarEvent))
            await session.execute(delete(ElectionCalendarCoverage))
            session.add(
                ElectionCalendarCoverage(
                    calendar_year=2026,
                    complete=True,
                    event_count=count,
                    expected_count=count,
                    page_count=1,
                    snapshot_revision="a" * 64,
                    fetched_at=fetched_at,
                )
            )
            session.add_all(
                [
                    ElectionCalendarEvent(
                        calendar_year=2026,
                        event_id=number,
                        category="Election Dates",
                        summary=f"Event {number}",
                        state=[],
                        start_date=date(2026, 11, number),
                        end_date_normalized=True,
                    )
                    for number in range(1, count + 1)
                ]
            )
        else:
            await session.execute(delete(ElectionCandidate))
            await session.execute(delete(ElectionCatalogCoverage))
            session.add(
                ElectionCatalogCoverage(
                    finance_cycle=2026,
                    complete=True,
                    candidate_count=count,
                    expected_count=count,
                    page_count=1,
                    snapshot_revision="b" * 64,
                    fetched_at=fetched_at,
                )
            )
            session.add_all(
                [
                    ElectionCandidate(
                        finance_cycle=2026,
                        candidate_id=f"H0CA{number:05d}",
                        name=f"Candidate {number}",
                        office="H",
                        state="CA",
                        district="01",
                        cycles=[2026],
                        election_years=[2026],
                        principal_committees=[],
                    )
                    for number in range(1, count + 1)
                ]
            )


async def _read_snapshot(session: AsyncSession, resource: str) -> tuple[int, int, list[str]]:
    if resource == "calendar":
        calendar = await list_election_calendar(db=session, year=2026)
        return (
            calendar.event_count,
            len(calendar.events),
            [str(event.event_id) for event in calendar.events],
        )
    candidates = await list_election_candidates(
        db=session,
        cycle=2026,
        election_year=None,
        office=None,
        state=None,
        district=None,
        party=None,
        q=None,
        limit=50,
        offset=0,
    )
    return (
        candidates.candidate_count,
        candidates.filtered_count,
        [candidate.candidate_id for candidate in candidates.candidates],
    )


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
@pytest.mark.parametrize("resource", ["candidates", "calendar"])
def test_election_response_keeps_one_snapshot_during_refresh(
    monkeypatch: pytest.MonkeyPatch, resource: str
) -> None:
    async def scenario() -> None:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=_TABLES))
            await _replace_snapshot(factory, resource, 1)

            async with factory() as reader:
                coverage_read = asyncio.Event()
                continue_read = asyncio.Event()
                execute = reader.execute

                async def pause_after_coverage(*args: Any, **kwargs: Any) -> Any:
                    result = await execute(*args, **kwargs)
                    if not coverage_read.is_set():
                        coverage_read.set()
                        await continue_read.wait()
                    return result

                monkeypatch.setattr(reader, "execute", pause_after_coverage)
                task = asyncio.create_task(_read_snapshot(reader, resource))
                try:
                    await asyncio.wait_for(coverage_read.wait(), timeout=10)
                    await _replace_snapshot(factory, resource, 2)
                    async with factory() as verifier:
                        table = ElectionCalendarEvent if resource == "calendar" else ElectionCandidate
                        stored_count = (
                            await verifier.execute(select(func.count()).select_from(table))
                        ).scalar_one()
                        assert stored_count == 2
                    continue_read.set()
                    response = await asyncio.wait_for(task, timeout=10)
                    expected_id = "1" if resource == "calendar" else "H0CA00001"
                    assert response == (1, 1, [expected_id])
                finally:
                    continue_read.set()
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        finally:
            try:
                async with engine.begin() as connection:
                    await connection.run_sync(
                        lambda sync: Base.metadata.drop_all(sync, tables=_TABLES)
                    )
            finally:
                await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
def test_legacy_calendar_writes_never_certify_raw_end_dates() -> None:
    async def scenario() -> None:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=_TABLES))
            async with factory.begin() as session:
                session.add(
                    ElectionCalendarCoverage(
                        calendar_year=2026,
                        complete=True,
                        event_count=1,
                        expected_count=1,
                        page_count=1,
                        snapshot_revision="a" * 64,
                        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
                    )
                )

            for normalized in (False, True, False):
                row: dict[str, object] = {
                    "calendar_year": 2026,
                    "event_id": 1,
                    "category": "Election Dates",
                    "summary": "Election",
                    "state": [],
                    "start_date": date(2026, 11, 3),
                    "end_date": date(2026, 11, 3 if normalized else 4),
                }
                if normalized:
                    row["end_date_normalized"] = True
                async with factory.begin() as session:
                    await session.execute(delete(ElectionCalendarEvent))
                    await session.execute(insert(ElectionCalendarEvent).values(**row))
                async with factory() as reader:
                    result = await list_election_calendar(db=reader, year=2026)
                    event = result.events[0]
                    assert event.end_date_normalized is normalized
                    assert event.end_date == (date(2026, 11, 3) if normalized else None)
        finally:
            try:
                async with engine.begin() as connection:
                    await connection.run_sync(
                        lambda sync: Base.metadata.drop_all(sync, tables=_TABLES)
                    )
            finally:
                await engine.dispose()

    asyncio.run(scenario())
