import asyncio
import json
import os
from collections.abc import Callable
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.member import Member, MemberTerm
from app.models.source_run import SourceRun
from app.normalize import members
from app.normalize.members import RosterLoad, plan_departures, to_term_rows
from app.pipelines import refresh
from app.pipelines.congress_legislators import LegislatorsPull
from app.schemas.member import LegislatorRaw

# --- the departure guard ---------------------------------------------------------


def test_no_departures_is_never_withheld() -> None:
    assert plan_departures({"A", "B"}, {"A", "B"}, roster_complete=False, allow_turnover=False) == (
        [],
        None,
    )


def test_departures_within_the_cap_are_applied() -> None:
    departed, withheld = plan_departures(
        {"A"}, {"A", "C", "B", "D"}, roster_complete=True, allow_turnover=False
    )
    assert (departed, withheld) == (["B", "C", "D"], None)


def test_departures_over_the_cap_need_confirmation() -> None:
    sitting = {"A", "B", "C", "D", "E"}
    departed, withheld = plan_departures({"A"}, sitting, roster_complete=True, allow_turnover=False)
    assert departed == ["B", "C", "D", "E"]
    assert withheld is not None and "--allow-roster-turnover" in withheld
    assert plan_departures({"A"}, sitting, roster_complete=True, allow_turnover=True) == (
        departed,
        None,
    )


def test_an_incomplete_roster_never_marks_anyone_departed() -> None:
    # Even a confirmed turnover: a record that failed validation would look departed.
    departed, withheld = plan_departures({"A"}, {"A", "B"}, roster_complete=False, allow_turnover=True)
    assert departed == ["B"]
    assert withheld is not None and "failed validation" in withheld


def test_withheld_reason_lists_a_bounded_number_of_ids() -> None:
    sitting = {f"M{i:06d}" for i in range(30)}
    _, withheld = plan_departures(set(), sitting, roster_complete=True, allow_turnover=False)
    assert withheld is not None and "(+18 more)" in withheld


def test_term_rows_are_deduplicated_on_the_unique_key(
    legislator: Callable[..., dict], term: Callable[..., dict]
) -> None:
    leg = LegislatorRaw.model_validate(
        legislator(
            terms=[
                term(start="2021-01-03", end="2023-01-03", district=3),
                # A corrected repeat of the same term: the later entry wins.
                term(start="2021-01-03", end="2022-06-30", district=3),
                term(type_="sen", start="2023-01-03", end="2029-01-03", district=None),
            ]
        )
    )
    rows = to_term_rows(leg, 17)
    assert [(r["chamber"], r["start_date"], r["end_date"]) for r in rows] == [
        ("house", date(2021, 1, 3), date(2022, 6, 30)),
        ("senate", date(2023, 1, 3), date(2029, 1, 3)),
    ]
    assert all(r["source_run_id"] == 17 for r in rows)
    assert rows[1]["district"] is None


# --- refresh_members ---------------------------------------------------------------


def _patch_refresh(monkeypatch: pytest.MonkeyPatch, roster: RosterLoad, skipped: int = 0) -> dict:
    mocks = {
        "_held_house_districts": AsyncMock(return_value={"WA-7"}),
        "normalize_and_load": AsyncMock(return_value=roster),
        "load_crosswalk": AsyncMock(),
        "load_committees": AsyncMock(),
        "record_run": AsyncMock(),
        "send_alert": AsyncMock(),
        "_alert_seat_changes": AsyncMock(),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(refresh, name, mock)
    monkeypatch.setattr(
        refresh.congress_legislators,
        "run",
        Mock(return_value=LegislatorsPull(legislators=535, skipped_legislators=skipped)),
    )
    return mocks


def test_refresh_members_records_applied_departures(monkeypatch: pytest.MonkeyPatch) -> None:
    mocks = _patch_refresh(monkeypatch, RosterLoad(count=535, departed=("B000001",), applied=True))

    asyncio.run(refresh.refresh_members())

    mocks["normalize_and_load"].assert_awaited_once_with(
        roster_complete=True, allow_turnover=False, source_run_id=None
    )
    mocks["record_run"].assert_awaited_once_with(
        "congress_legislators", 535, "ok", "marked 1 member(s) departed: B000001"
    )
    mocks["send_alert"].assert_not_awaited()
    mocks["_alert_seat_changes"].assert_awaited_once()


def test_refresh_members_withholds_and_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    roster = RosterLoad(count=530, departed=("B000001",), applied=False, withheld="needs review")
    mocks = _patch_refresh(monkeypatch, roster, skipped=2)

    with pytest.raises(refresh.RosterChangeWithheldError, match="needs review"):
        asyncio.run(refresh.refresh_members(allow_roster_turnover=True))

    mocks["normalize_and_load"].assert_awaited_once_with(
        roster_complete=False, allow_turnover=True, source_run_id=None
    )
    mocks["record_run"].assert_awaited_once_with("congress_legislators", 530, "partial", "needs review")
    mocks["send_alert"].assert_awaited_once()
    mocks["_alert_seat_changes"].assert_not_awaited()


# --- against PostgreSQL ---------------------------------------------------------

_needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
_TABLES = [SourceRun.__table__, Member.__table__, MemberTerm.__table__]


@_needs_postgres
def test_roster_load_applies_guarded_departures_and_terms(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    legislator: Callable[..., dict],
    term: Callable[..., dict],
) -> None:
    staging = tmp_path / "legislators_raw.json"
    monkeypatch.setattr(members, "STAGING_PATH", staging)

    def stage(ids: list[str], first_end: str = "2023-01-03") -> None:
        staging.write_text(
            json.dumps(
                [
                    legislator(
                        bioguide=bid,
                        terms=[
                            term(start="2021-01-03", end=first_end, district=i + 1),
                            term(start="2023-01-03", end="2027-01-03", district=i + 1),
                        ],
                    )
                    for i, bid in enumerate(ids)
                ]
            )
        )

    ids = [f"X00000{i}" for i in range(6)]

    async def check() -> None:
        url = os.environ["TEST_DATABASE_URL"]
        assert url.startswith("postgresql+asyncpg://")
        engine = create_async_engine(url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(members, "async_session_factory", factory)

        async def sitting() -> set[str]:
            async with factory() as session:
                return set(
                    (
                        await session.execute(
                            select(Member.bioguide_id).where(Member.in_office.is_(True))
                        )
                    ).scalars()
                )

        try:
            # This database belongs exclusively to the CI job, not the app.
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=_TABLES))

            stage(ids)
            load = await members.normalize_and_load(roster_complete=True)
            assert (load.count, load.departed, load.applied) == (6, (), True)
            assert await sitting() == set(ids)

            # Four missing members exceed the cap: withheld, nobody marked departed.
            stage(ids[:2], first_end="2022-12-31")
            load = await members.normalize_and_load(roster_complete=True)
            assert load.departed == tuple(ids[2:]) and not load.applied
            assert await sitting() == set(ids)

            load = await members.normalize_and_load(roster_complete=True, allow_turnover=True)
            assert load.applied
            assert await sitting() == set(ids[:2])

            # A member who returns is back in office.
            stage(ids[:3])
            await members.normalize_and_load(roster_complete=True)
            assert await sitting() == set(ids[:3])

            async with factory() as session:
                terms = (
                    await session.execute(
                        select(MemberTerm.bioguide_id, MemberTerm.start_date, MemberTerm.end_date)
                        .order_by(MemberTerm.bioguide_id, MemberTerm.start_date)
                    )
                ).all()
            # Terms are kept for departed members and updated in place, never duplicated.
            assert len(terms) == 12
            assert terms[0] == (ids[0], date(2021, 1, 3), date(2023, 1, 3))
            assert terms[-2] == (ids[5], date(2021, 1, 3), date(2023, 1, 3))
        finally:
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.drop_all(sync, tables=_TABLES))
            await engine.dispose()

    asyncio.run(check())
