import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app import scheduler
from app.config import settings
from app.db import Base
from app.models.source_run import SourceRun
from app.pipelines import refresh, runs
from app.pipelines.batch import BatchResult
from app.routers import pipeline_status

# --- pure helpers -------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "detail", "error", "expected"),
    [
        ("ok", None, None, ("ok", None)),
        ("partial", "2 of 9 bills failed", None, ("partial", "2 of 9 bills failed")),
        # Raised after recording partial (incomplete votes, withheld roster): stays partial.
        ("partial", "chamber(s) failed: house", RuntimeError("x"), ("partial", "chamber(s) failed: house")),
        ("error", "upstream 503", RuntimeError("upstream 503"), ("error", "upstream 503")),
        # Raised after recording ok (e.g. a later step failed): the run failed.
        ("ok", None, RuntimeError("boom"), ("error", "RuntimeError: boom")),
        (None, None, ValueError("bad"), ("error", "ValueError: bad")),
        (None, None, None, ("error", "no outcome recorded")),
        ("stale", "x", None, ("error", "unexpected status 'stale': x")),
        # Cancelled by a stopping worker: interrupted, not failed.
        (None, None, asyncio.CancelledError(), ("abandoned", "cancelled before it finished (the process was stopping)")),
        ("ok", None, asyncio.CancelledError(), ("abandoned", "cancelled before it finished (the process was stopping)")),
        ("partial", "1 of 4 failed", asyncio.CancelledError(), ("partial", "1 of 4 failed")),
    ],
)
def test_final_outcome(
    outcome: str | None,
    detail: str | None,
    error: BaseException | None,
    expected: tuple[str, str | None],
) -> None:
    run = runs._ActiveRun(source="votes", run_id=1, outcome=outcome, detail=detail)
    assert runs.final_outcome(run, error) == expected


def test_redact_removes_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "fec-secret-value-123")
    text = (
        "GET https://api.example.gov/v1?api_key=abc123&page=2 failed; "
        "token=zzz; Authorization: Bearer abcdefghijkl; "
        "postgresql://user:pw@db:5432/x; header fec-secret-value-123"
    )
    out = runs.redact(text)
    assert out is not None
    for secret in ("abc123", "zzz", "abcdefghijkl", "user:pw", "fec-secret-value-123"):
        assert secret not in out
    assert "page=2" in out
    assert runs.redact(None) is None
    assert len(runs.redact("x" * 10_000) or "") <= 4001


def test_input_manifest_hashes_present_files_and_marks_missing(tmp_path: Path) -> None:
    present = tmp_path / "bills_raw.json"
    present.write_bytes(b"[]")
    manifest = runs.input_manifest((present, tmp_path / "missing.json"))
    assert manifest[0]["name"] == "bills_raw.json"
    assert manifest[0]["bytes"] == 2
    assert manifest[0]["sha256"] == (
        "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    )
    assert manifest[0]["modified_at"]
    assert manifest[1] == {
        "name": "missing.json", "sha256": None, "bytes": None, "modified_at": None
    }


def test_outcomes_only_reach_the_matching_active_run() -> None:
    run = runs._ActiveRun(source="votes", run_id=7)
    token = runs._active.set(run)
    try:
        runs.note_outcome("congress_gov_bills", 5, "ok", None)
        assert run.outcome is None
        runs.note_outcome("votes", 12, "partial", "senate fallback")
        runs.note_batch("votes", BatchResult(total=3, succeeded=2, failed=1))
        assert runs.current_run_id() == 7
    finally:
        runs._active.reset(token)
    assert (run.outcome, run.record_count, run.detail) == ("partial", 12, "senate fallback")
    assert run.batch == BatchResult(total=3, succeeded=2, failed=1)
    assert runs.current_run_id() is None


@pytest.mark.parametrize(
    "error",
    [
        refresh.RosterChangeWithheldError("held"),
        runs.RunSkippedError("busy"),
        refresh.fec_candidates.CandidateSnapshotIncompleteError("incomplete candidates"),
        refresh.fec_election_calendar.CalendarSnapshotIncompleteError("incomplete calendar"),
        refresh.fec_candidate_totals.CampaignMoneySnapshotIncompleteError("incomplete money"),
    ],
)
def test_nonretryable_refresh_errors_are_attempted_once(error: Exception) -> None:
    fn = AsyncMock(side_effect=error)
    assert asyncio.run(refresh._run_with_retry("members", fn, delay=0)) is False
    assert fn.await_count == 1


def test_scheduled_jobs_record_their_trigger_and_tolerate_skips() -> None:
    seen: list[str] = []

    async def job() -> None:
        seen.append(runs.run_trigger.get())
        raise runs.RunSkippedError("busy")

    asyncio.run(scheduler._guarded(job, "probe")())
    assert seen == ["schedule"]
    assert runs.run_trigger.get() == "manual"


# --- against PostgreSQL ---------------------------------------------------------

_needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
_TABLES = [SourceRun.__table__]


async def _with_run_table(
    check: Callable[[AsyncEngine], Awaitable[None]], monkeypatch: pytest.MonkeyPatch
) -> None:
    url = os.environ["TEST_DATABASE_URL"]
    assert url.startswith("postgresql+asyncpg://")
    engine = create_async_engine(url, poolclass=NullPool)
    monkeypatch.setattr(runs, "_lock_engine", engine)
    try:
        # This database belongs exclusively to the CI job, not the app.
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=_TABLES))
        await check(engine)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.drop_all(sync, tables=_TABLES))
        await engine.dispose()


async def _rows(engine: AsyncEngine) -> list:
    async with engine.connect() as connection:
        return list(
            (await connection.execute(select(SourceRun).order_by(SourceRun.id))).all()
        )


async def _lock_is_free(engine: AsyncEngine, source: str) -> bool:
    async with engine.connect() as connection:
        got = (
            await connection.execute(select(func.pg_try_advisory_lock(*runs._lock_args(source))))
        ).scalar_one()
        if got:
            await connection.execute(select(func.pg_advisory_unlock(*runs._lock_args(source))))
        return bool(got)


@_needs_postgres
def test_a_tracked_run_records_history(monkeypatch: pytest.MonkeyPatch) -> None:
    async def check(engine: AsyncEngine) -> None:
        now = datetime.now(UTC)
        async with engine.begin() as connection:
            await connection.execute(
                insert(SourceRun),
                [
                    # Left 'running' by a process that died.
                    {"source": "votes", "trigger": "schedule", "outcome": "running",
                     "started_at": now - timedelta(hours=1)},
                    {"source": "votes", "trigger": "schedule", "outcome": "ok",
                     "started_at": now - timedelta(days=401)},
                    {"source": "votes", "trigger": "schedule", "outcome": "ok",
                     "started_at": now - timedelta(days=399)},
                    {"source": "congress_gov_bills", "trigger": "schedule", "outcome": "ok",
                     "started_at": now - timedelta(days=401)},
                ],
            )

        async def refresh_votes() -> None:
            assert runs.current_run_id() is not None
            assert not await _lock_is_free(engine, "votes")
            runs.note_batch("votes", BatchResult(total=10, succeeded=9, failed=1))
            runs.note_outcome("votes", 42, "ok", None)

        await runs.tracked("votes", refresh_votes)()

        rows = await _rows(engine)
        assert [(r.source, r.outcome) for r in rows] == [
            ("votes", "abandoned"),
            ("votes", "ok"),  # the 399-day-old row survives the 400-day prune
            ("congress_gov_bills", "ok"),  # another source's rows are untouched
            ("votes", "ok"),
        ]
        latest = rows[-1]
        assert latest.trigger == "manual"
        assert latest.finished_at is not None
        assert (latest.record_count, latest.items_total, latest.items_succeeded,
                latest.items_failed) == (42, 10, 9, 1)
        assert [i["name"] for i in latest.inputs] == [
            "house_votes_raw.json", "senate_votes_raw.json"
        ]
        assert await _lock_is_free(engine, "votes")

    asyncio.run(_with_run_table(check, monkeypatch))


@_needs_postgres
def test_a_failed_run_is_recorded_and_releases_the_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "congress_gov_api_key", "congress-secret-key")

    async def check(engine: AsyncEngine) -> None:
        async def refresh_bills() -> None:
            raise RuntimeError("upstream rejected congress-secret-key")

        with pytest.raises(RuntimeError):
            await runs.tracked("congress_gov_bills", refresh_bills)()
        (row,) = await _rows(engine)
        assert row.outcome == "error"
        assert row.detail == "RuntimeError: upstream rejected [REDACTED]"
        assert row.inputs is None
        assert await _lock_is_free(engine, "congress_gov_bills")

    asyncio.run(_with_run_table(check, monkeypatch))


@_needs_postgres
def test_an_overlapping_run_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    async def check(engine: AsyncEngine) -> None:
        called = AsyncMock()
        async with engine.connect() as holder:
            await holder.execute(select(func.pg_advisory_lock(*runs._lock_args("fec_finance"))))
            token = runs.run_trigger.set("schedule")
            try:
                with pytest.raises(runs.RunSkippedError):
                    await runs.tracked("fec_finance", called)()
            finally:
                runs.run_trigger.reset(token)
            # A different source is not blocked.
            await runs.tracked("zip_districts", AsyncMock())()
            await holder.execute(select(func.pg_advisory_unlock(*runs._lock_args("fec_finance"))))
        called.assert_not_awaited()
        rows = await _rows(engine)
        assert [(r.source, r.trigger, r.outcome) for r in rows] == [
            ("fec_finance", "schedule", "skipped"),
            # Finished without reporting an outcome.
            ("zip_districts", "manual", "error"),
        ]
        assert rows[1].detail == "no outcome recorded"

    asyncio.run(_with_run_table(check, monkeypatch))


@_needs_postgres
def test_source_run_history_filters_and_pages_newest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def check(engine: AsyncEngine) -> None:
        now = datetime.now(UTC)
        manifest = [{"name": "house_votes_raw.json", "sha256": None, "bytes": None,
                     "modified_at": None}]
        async with AsyncSession(engine) as session:
            await session.execute(
                insert(SourceRun),
                [
                    {"source": "votes", "trigger": "schedule", "outcome": "ok",
                     "started_at": now - timedelta(hours=4)},
                    {"source": "congress_gov_bills", "trigger": "schedule",
                     "outcome": "error", "started_at": now - timedelta(hours=3),
                     "detail": "upstream 503"},
                    {"source": "votes", "trigger": "manual", "outcome": "partial",
                     "started_at": now - timedelta(hours=2),
                     "finished_at": now - timedelta(hours=1), "record_count": 12,
                     "items_total": 3, "items_succeeded": 2, "items_failed": 1,
                     "inputs": manifest},
                    {"source": "votes", "trigger": "schedule", "outcome": "ok",
                     "started_at": now - timedelta(hours=1)},
                ],
            )
            await session.commit()

        async with AsyncSession(engine) as session:

            async def fetch(**params: object) -> list[dict]:
                query = pipeline_status.SourceRunQuery.model_validate(params)
                return await pipeline_status.source_runs(query, db=session)

            everything = await fetch()
            ids = [run["id"] for run in everything]
            assert ids == sorted(ids, reverse=True)
            assert [(run["source"], run["outcome"]) for run in everything] == [
                ("votes", "ok"),
                ("votes", "partial"),
                ("congress_gov_bills", "error"),
                ("votes", "ok"),
            ]

            votes = await fetch(source="votes")
            assert [run["outcome"] for run in votes] == ["ok", "partial", "ok"]
            (failed,) = await fetch(outcome="error")
            assert (failed["source"], failed["detail"]) == ("congress_gov_bills", "upstream 503")
            assert failed["finished_at"] is None

            first = await fetch(source="votes", limit=2)
            rest = await fetch(source="votes", limit=2, before_id=first[-1]["id"])
            assert [run["id"] for run in first + rest] == [run["id"] for run in votes]

            partial = first[1]
            assert partial["trigger"] == "manual"
            assert datetime.fromisoformat(partial["started_at"]) < datetime.fromisoformat(
                partial["finished_at"]
            )
            assert (partial["record_count"], partial["items_total"],
                    partial["items_succeeded"], partial["items_failed"]) == (12, 3, 2, 1)
            assert partial["inputs"] == manifest

    asyncio.run(_with_run_table(check, monkeypatch))
