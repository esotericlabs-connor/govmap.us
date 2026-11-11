import asyncio
import logging
import multiprocessing
import os
from collections.abc import Iterator
from datetime import timedelta
from multiprocessing.connection import Connection

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.db import Base
from app.models.upstream_budget import UpstreamBudget, UpstreamRequest
from app.services import upstream
from app.services.upstream import (
    UpstreamBudgetUnavailableError,
    UpstreamCapacityError,
    reserve_request,
)

_TABLES = [UpstreamBudget.__table__, UpstreamRequest.__table__]


@pytest.fixture
def db() -> Iterator[AsyncEngine]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("isolated CI PostgreSQL only")
    assert url.startswith("postgresql+asyncpg://")
    engine = create_async_engine(url, poolclass=NullPool)

    async def create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=_TABLES))
            await conn.execute(
                insert(UpstreamBudget),
                [{"source": source} for source in ("congress", "fec", "govinfo")],
            )
            await conn.execute(
                update(UpstreamBudget).values(
                    initialized_at=func.clock_timestamp() - timedelta(hours=2)
                )
            )

    async def drop() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync: Base.metadata.drop_all(sync, tables=_TABLES))
        await engine.dispose()

    try:
        asyncio.run(create())
        yield engine
    finally:
        asyncio.run(drop())


async def _count(db: AsyncEngine) -> int:
    async with db.connect() as conn:
        return (await conn.execute(select(func.count()).select_from(UpstreamRequest))).scalar_one()


def _child_reservation(url: str, channel: Connection) -> None:
    async def run() -> bool:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            try:
                await reserve_request("fec", "worker", 3, 4, engine)
            except UpstreamBudgetUnavailableError:
                raise
            except UpstreamCapacityError:
                return False
            return True
        finally:
            await engine.dispose()

    try:
        channel.send(asyncio.run(run()))
    finally:
        channel.close()


def test_all_processes_share_the_worker_allowance(db: AsyncEngine) -> None:
    context = multiprocessing.get_context("spawn")
    children = []
    readers = []
    try:
        for _ in range(8):
            reader, writer = context.Pipe(duplex=False)
            process = context.Process(
                target=_child_reservation, args=(os.environ["TEST_DATABASE_URL"], writer)
            )
            process.start()
            writer.close()
            children.append(process)
            readers.append(reader)
        results = []
        for reader in readers:
            assert reader.poll(30), "a request admission process did not return"
            results.append(reader.recv())
        for process in children:
            process.join(10)
            assert process.exitcode == 0
        assert sum(results) == 3
        assert asyncio.run(_count(db)) == 3
    finally:
        for process in children:
            if process.is_alive():
                process.terminate()
            process.join(10)
        for reader in readers:
            reader.close()


def test_worker_cannot_borrow_api_capacity_and_total_covers_all_scopes(db: AsyncEngine) -> None:
    async def scenario() -> None:
        for _ in range(3):
            await reserve_request("fec", "worker", 3, 4, db)
        with pytest.raises(UpstreamCapacityError):
            await reserve_request("fec", "worker", 3, 4, db)
        await reserve_request("fec", "api", 1, 4, db)
        with pytest.raises(UpstreamCapacityError):
            await reserve_request("fec", "shared", 4, 4, db)
        await reserve_request("congress", "worker", 1, 1, db)
        assert await _count(db) == 5

    asyncio.run(scenario())


def test_usage_survives_engine_restart_and_failed_or_cancelled_work(db: AsyncEngine) -> None:
    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="HTTP failed"):
            await reserve_request("fec", "worker", 2, 3, db)
            raise RuntimeError("HTTP failed")
        started = asyncio.Event()

        async def work() -> None:
            await reserve_request("fec", "worker", 2, 3, db)
            started.set()
            await asyncio.sleep(3600)

        task = asyncio.create_task(work())
        try:
            await asyncio.wait_for(started.wait(), 5)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await db.dispose()
        replacement = create_async_engine(os.environ["TEST_DATABASE_URL"], poolclass=NullPool)
        try:
            with pytest.raises(UpstreamCapacityError):
                await reserve_request("fec", "worker", 2, 3, replacement)
            assert await _count(replacement) == 2
        finally:
            await replacement.dispose()

    asyncio.run(scenario())


def test_only_attempts_at_least_one_hour_old_expire(db: AsyncEngine) -> None:
    async def scenario() -> None:
        await reserve_request("fec", "worker", 1, 1, db)
        async with db.begin() as conn:
            await conn.execute(
                update(UpstreamRequest).values(
                    started_at=func.clock_timestamp() - timedelta(minutes=59)
                )
            )
        with pytest.raises(UpstreamCapacityError) as caught:
            await reserve_request("fec", "worker", 1, 1, db)
        assert 55 <= caught.value.retry_after <= 60
        async with db.begin() as conn:
            await conn.execute(
                update(UpstreamRequest).values(
                    started_at=func.clock_timestamp() - timedelta(hours=1)
                )
            )
        await reserve_request("fec", "worker", 1, 1, db)
        assert await _count(db) == 1

    asyncio.run(scenario())


def test_lowered_limit_waits_for_enough_reservations_to_expire(db: AsyncEngine) -> None:
    async def scenario() -> None:
        async with db.begin() as conn:
            now = (await conn.execute(select(func.clock_timestamp()))).scalar_one()
            await conn.execute(
                insert(UpstreamRequest),
                [
                    {"source": "fec", "scope": "worker", "started_at": now - timedelta(seconds=age)}
                    for age in (3500, 3000, 1000)
                ],
            )
        with pytest.raises(UpstreamCapacityError) as caught:
            await reserve_request("fec", "worker", 1, 4, db)
        assert 2595 <= caught.value.retry_after <= 2600
        assert await _count(db) == 3

    asyncio.run(scenario())


def test_first_migration_holds_for_one_hour_but_restart_does_not(db: AsyncEngine) -> None:
    async def scenario() -> None:
        async with db.begin() as conn:
            await conn.execute(
                update(UpstreamBudget).values(initialized_at=func.clock_timestamp())
            )
        with pytest.raises(UpstreamCapacityError) as caught:
            await reserve_request("fec", "worker", 2, 3, db)
        assert "one-hour rollout hold" in str(caught.value)
        assert 3595 <= caught.value.retry_after <= 3600
        assert await _count(db) == 0
        async with db.begin() as conn:
            await conn.execute(
                update(UpstreamBudget).values(
                    initialized_at=func.clock_timestamp() - timedelta(hours=1)
                )
            )
        await reserve_request("fec", "worker", 2, 3, db)
        await db.dispose()
        await reserve_request("fec", "worker", 2, 3, db)
        assert await _count(db) == 2

    asyncio.run(scenario())


def test_missing_source_state_fails_closed(db: AsyncEngine, caplog: pytest.LogCaptureFixture) -> None:
    async def scenario() -> None:
        async with db.begin() as conn:
            await conn.execute(delete(UpstreamBudget).where(UpstreamBudget.source == "fec"))
        with pytest.raises(UpstreamBudgetUnavailableError):
            await reserve_request("fec", "worker", 2, 3, db)
        assert await _count(db) == 0

    asyncio.run(scenario())
    assert "no initialized source row" in caplog.text


def test_database_failure_is_explicit_and_redacted(
    db: AsyncEngine, caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        async with db.begin() as conn:
            await conn.run_sync(UpstreamRequest.__table__.drop)
        with pytest.raises(UpstreamBudgetUnavailableError) as caught:
            await reserve_request("fec", "worker", 2, 3, db)
        assert caught.value.retry_after == 5
        assert str(caught.value) == "fec shared request budget unavailable"
        assert caught.value.__suppress_context__

    caplog.set_level(logging.WARNING, logger="app.services.upstream")
    asyncio.run(scenario())
    assert "shared request budget unavailable" in caplog.text
    assert os.environ["TEST_DATABASE_URL"] not in caplog.text
    assert "[SQL:" not in caplog.text


def test_blocked_admission_is_bounded_and_does_not_spend_quota(
    db: AsyncEngine, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upstream, "ADMISSION_TIMEOUT_SECONDS", 0.1)

    async def scenario() -> None:
        async with db.begin() as conn:
            await conn.execute(
                select(UpstreamBudget.source)
                .where(UpstreamBudget.source == "fec")
                .with_for_update()
            )
            with pytest.raises(UpstreamBudgetUnavailableError):
                await asyncio.wait_for(reserve_request("fec", "worker", 2, 3, db), 2)
        assert await _count(db) == 0
        monkeypatch.setattr(upstream, "ADMISSION_TIMEOUT_SECONDS", 5)
        await reserve_request("fec", "worker", 2, 3, db)
        assert await _count(db) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("source", ["congress", "fec", "govinfo"])
def test_scope_limit_cannot_exceed_the_total(source: str) -> None:
    values = {f"{source}_requests_per_hour": 3, f"total_{source}_requests_per_hour": 2}
    with pytest.raises(ValidationError, match="share cannot exceed"):
        Settings(_env_file=None, **values)


def test_unknown_budget_scope_fails_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, upstream_budget_scope="manual-extra-budget")


def test_budget_validation_does_not_log_other_settings() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:private-placeholder@localhost/db",
            fec_requests_per_hour=3,
            total_fec_requests_per_hour=2,
        )
    assert "private-placeholder" not in str(caught.value)
    assert "input_value" not in str(caught.value)
