import asyncio
import os
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.models.contribution import Contribution, DonationFetch
from app.services import donations

BIOGUIDE = "A000001"
CYCLE = 2026
COMMITTEE = "C00000001"


def _receipt(sub_id: str, amount: float) -> dict[str, Any]:
    return {
        "sub_id": sub_id,
        "contributor_name": f"Donor {sub_id}",
        "contribution_receipt_amount": amount,
        "contribution_receipt_date": "2026-01-15",
    }


# With _PER_PAGE patched to 2: a full first page, then a short final page.
_PAGE_1 = {
    "results": [_receipt("S1", 500.0), _receipt("S2", 400.0)],
    "pagination": {
        "count": 3,
        "last_indexes": {"last_index": "I2", "last_contribution_receipt_amount": 400.0},
    },
}
_PAGE_2 = {
    "results": [_receipt("S3", 300.0)],
    "pagination": {"count": 3, "last_indexes": {}},
}


def _page_for(params: dict[str, Any]) -> dict[str, Any]:
    return _PAGE_2 if params.get("last_index") == "I2" else _PAGE_1


def _snapshot(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "bioguide_id": BIOGUIDE,
        "committee_id": COMMITTEE,
        "complete": False,
        "fetched_count": 0,
        "total_count": None,
        "cursor_index": None,
        "cursor_amount": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_lost_cursor_race_discards_page_and_adopts_committed_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(donations, "_PER_PAGE", 2)
    monkeypatch.setattr(
        donations, "run_upstream", AsyncMock(side_effect=lambda *a, **p: _page_for(p))
    )
    committed = {
        "fetched_count": 3,
        "total_count": 3,
        "complete": True,
        "cursor_index": "I2",
        "cursor_amount": "400.0",
    }
    db = Mock()
    db.execute = AsyncMock(
        side_effect=[
            Mock(scalars=lambda: SimpleNamespace(all=lambda: [])),  # duplicate receipts
            SimpleNamespace(rowcount=0),  # compare-and-set lost
            SimpleNamespace(one=lambda: SimpleNamespace(_mapping=committed)),
        ]
    )
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    state = _snapshot()

    asyncio.run(donations._fetch_more(db, state, CYCLE, until=50))

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
    for key, value in committed.items():
        assert getattr(state, key) == value


def test_each_page_commits_with_its_cursor_before_the_next_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(donations, "_PER_PAGE", 2)
    events: list[str] = []

    async def fetch(*_args: Any, **params: Any) -> dict[str, Any]:
        events.append(f"fetch:{params.get('last_index')}")
        return _page_for(params)

    async def commit() -> None:
        events.append("commit")

    monkeypatch.setattr(donations, "run_upstream", fetch)
    db = Mock()
    db.execute = AsyncMock(
        side_effect=[
            Mock(scalars=lambda: SimpleNamespace(all=lambda: ["S1", "S2"])),
            SimpleNamespace(rowcount=1),
            Mock(scalars=lambda: SimpleNamespace(all=lambda: ["S3"])),
            SimpleNamespace(rowcount=1),
        ]
    )
    db.commit = AsyncMock(side_effect=commit)
    db.rollback = AsyncMock()
    state = _snapshot()

    asyncio.run(donations._fetch_more(db, state, CYCLE, until=50))

    assert events == ["fetch:None", "commit", "fetch:I2", "commit"]
    assert (state.fetched_count, state.total_count, state.complete) == (3, 3, True)
    # A completed ledger keeps the last cursor it actually followed.
    assert (state.cursor_index, state.cursor_amount) == ("I2", "400.0")
    db.rollback.assert_not_awaited()


@pytest.mark.parametrize(
    "page",
    [
        {},
        {"results": [], "pagination": {}},
        {"results": [{"sub_id": None}], "pagination": {"count": 1}},
        {"results": [{"sub_id": ""}], "pagination": {"count": 1}},
        {"results": _PAGE_1["results"], "pagination": {"count": 20}},
        {
            "results": _PAGE_1["results"],
            "pagination": {
                "count": 20,
                "last_indexes": {"last_index": "I0"},
            },
        },
        {
            "results": _PAGE_1["results"],
            "pagination": {
                "count": 20,
                "last_indexes": {
                    "last_index": "I0", "last_contribution_receipt_amount": 700.0
                },
            },
        },
    ],
)
def test_invalid_page_never_publishes_or_completes_the_ledger(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, page: dict[str, Any]
) -> None:
    monkeypatch.setattr(donations, "_PER_PAGE", 2)
    monkeypatch.setattr(donations, "run_upstream", AsyncMock(return_value=page))
    state = _snapshot(cursor_index="I0", cursor_amount="700.0")
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    asyncio.run(donations._fetch_more(db, state, CYCLE, until=50))

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    assert (state.fetched_count, state.complete, state.cursor_index) == (0, False, "I0")
    assert "invalid schedule_a page" in caplog.text


_needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
_TABLES = [Contribution.__table__, DonationFetch.__table__]


async def _with_ledger_tables(
    check: Callable[[async_sessionmaker[AsyncSession]], Awaitable[None]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = os.environ["TEST_DATABASE_URL"]
    assert url.startswith("postgresql+asyncpg://")
    monkeypatch.setattr(settings, "fec_api_key", "test-placeholder")
    monkeypatch.setattr(donations, "_PER_PAGE", 2)
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        # This database belongs exclusively to the CI job, not the app.
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(sync, tables=_TABLES)
            )
        async with factory() as session:
            session.add(
                DonationFetch(
                    bioguide_id=BIOGUIDE,
                    cycle=CYCLE,
                    committee_id=COMMITTEE,
                    resolved=True,
                    fetched_count=0,
                    complete=False,
                )
            )
            await session.commit()
        await check(factory)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: Base.metadata.drop_all(sync, tables=_TABLES)
            )
        await engine.dispose()


@_needs_postgres
def test_ledger_fetch_holds_no_transaction_across_fec_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def check(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory() as session:
            async def fetch(*_args: Any, **params: Any) -> dict[str, Any]:
                assert not session.in_transaction()
                return _page_for(params)

            monkeypatch.setattr(donations, "run_upstream", fetch)
            ledger = await donations.get_donations(session, BIOGUIDE, CYCLE, 0, 50)

        assert [item["sub_id"] for item in ledger["items"]] == ["S1", "S2", "S3"]
        assert (ledger["total"], ledger["cached"], ledger["complete"]) == (3, 3, True)
        async with factory() as session:
            row = await session.get(DonationFetch, (BIOGUIDE, CYCLE))
            assert row is not None
            assert (row.fetched_count, row.complete, row.cursor_index) == (3, True, "I2")

    asyncio.run(_with_ledger_tables(check, monkeypatch))


@_needs_postgres
def test_stale_concurrent_fetch_cannot_regress_a_completed_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        donations, "run_upstream", AsyncMock(side_effect=lambda *a, **p: _page_for(p))
    )

    async def detached(factory: async_sessionmaker[AsyncSession]) -> DonationFetch:
        async with factory() as session:
            state = await session.get(DonationFetch, (BIOGUIDE, CYCLE))
            assert state is not None
            await session.commit()
            session.expunge(state)
            return state

    async def check(factory: async_sessionmaker[AsyncSession]) -> None:
        winner = await detached(factory)
        stale = await detached(factory)
        async with factory() as session:
            await donations._fetch_more(session, winner, CYCLE, until=50)
        assert winner.complete
        async with factory() as session:
            # Starts from the stale fetched_count=0 snapshot and re-reads page 1.
            await donations._fetch_more(session, stale, CYCLE, until=50)
        assert (stale.fetched_count, stale.complete, stale.cursor_index) == (3, True, "I2")

        async with factory() as session:
            row = await session.get(DonationFetch, (BIOGUIDE, CYCLE))
            assert row is not None
            assert (row.fetched_count, row.total_count, row.complete) == (3, 3, True)
            assert (row.cursor_index, row.cursor_amount) == ("I2", "400.0")
            stored = await session.scalar(select(func.count()).select_from(Contribution))
            assert stored == 3

    asyncio.run(_with_ledger_tables(check, monkeypatch))


@_needs_postgres
def test_duplicate_receipts_do_not_inflate_cached_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch(*_args: Any, **params: Any) -> dict[str, Any]:
        if params.get("last_index") == "I2":
            return _PAGE_2
        return {
            "results": [_receipt("S1", 500.0), _receipt("S1", 500.0)],
            "pagination": _PAGE_1["pagination"],
        }

    # Two distinct receipts, despite the duplicate in the first source page.
    async def check(factory: async_sessionmaker[AsyncSession]) -> None:
        async def duplicate_pages(*args: Any, **params: Any) -> dict[str, Any]:
            page = await fetch(*args, **params)
            return {**page, "pagination": {**page["pagination"], "count": 2}}

        monkeypatch.setattr(donations, "run_upstream", duplicate_pages)
        async with factory() as session:
            ledger = await donations.get_donations(session, BIOGUIDE, CYCLE, 0, 50)
        assert (ledger["cached"], ledger["complete"]) == (2, True)
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(Contribution)) == 2

    asyncio.run(_with_ledger_tables(check, monkeypatch))


@_needs_postgres
def test_overlapping_requests_publish_one_consistent_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def check(factory: async_sessionmaker[AsyncSession]) -> None:
        both_started = asyncio.Event()
        started = 0

        async def fetch(*_args: Any, **params: Any) -> dict[str, Any]:
            nonlocal started
            if not params.get("last_index"):
                started += 1
                if started == 2:
                    both_started.set()
                await both_started.wait()
            return _page_for(params)

        monkeypatch.setattr(donations, "run_upstream", fetch)
        async with factory() as first, factory() as second:
            async with asyncio.timeout(10):
                await asyncio.gather(
                    donations.get_donations(first, BIOGUIDE, CYCLE, 0, 50),
                    donations.get_donations(second, BIOGUIDE, CYCLE, 0, 50),
                )
        async with factory() as session:
            state = await session.get(DonationFetch, (BIOGUIDE, CYCLE))
            assert state is not None
            assert (state.fetched_count, state.complete, state.cursor_index) == (3, True, "I2")
            assert await session.scalar(select(func.count()).select_from(Contribution)) == 3

    asyncio.run(_with_ledger_tables(check, monkeypatch))


@_needs_postgres
def test_short_page_with_missing_records_preserves_the_last_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch(*_args: Any, **params: Any) -> dict[str, Any]:
        if params.get("last_index"):
            return {"results": [], "pagination": {"count": 3}}
        return _PAGE_1

    async def check(factory: async_sessionmaker[AsyncSession]) -> None:
        monkeypatch.setattr(donations, "run_upstream", fetch)
        async with factory() as session:
            ledger = await donations.get_donations(session, BIOGUIDE, CYCLE, 0, 50)
        assert (ledger["cached"], ledger["complete"]) == (2, False)
        async with factory() as session:
            state = await session.get(DonationFetch, (BIOGUIDE, CYCLE))
            assert state is not None
            assert state.cursor_index == "I2"
            assert await session.scalar(select(func.count()).select_from(Contribution)) == 2

    asyncio.run(_with_ledger_tables(check, monkeypatch))
