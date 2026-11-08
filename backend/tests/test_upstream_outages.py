"""Regression tests for Congress.gov outage handling.

A Congress.gov read-timeout storm once held a deploy for 2h12m: every bill paid a
full 30s timeout, the loop never gave up, and the run was still recorded 'ok'.
These pin the fixes — timeouts classified as outages, batch loops that stop
early, degraded runs recorded as 'partial', and outages never retried blindly.
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import requests

from app.config import settings
from app.pipelines import (
    congress_committee_meetings,
    congress_gov_bills,
    congress_member_sponsored,
    refresh,
)
from app.pipelines.batch import BatchResult, OutageBreaker
from app.services import bill_enrich, upstream
from app.services.upstream import UpstreamUnavailableError, _Budget

_SECRET = "test-placeholder-key"


def _outage() -> UpstreamUnavailableError:
    return UpstreamUnavailableError("congress", "bill/119/hr/1: ReadTimeout")


@pytest.fixture
def congress_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "congress_gov_api_key", _SECRET)
    monkeypatch.setattr(settings, "congress_max_consecutive_failures", 3)
    monkeypatch.setitem(upstream._BUDGETS, "congress", _Budget("congress", 1000, 4))


@pytest.mark.parametrize(
    "error",
    [requests.ReadTimeout, requests.ConnectTimeout, requests.ConnectionError],
)
def test_get_turns_timeouts_into_unretried_outage(
    congress_env: None, monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    get = Mock(side_effect=error(f"read timed out for /v3/bill?api_key={_SECRET}"))
    monkeypatch.setattr(congress_gov_bills._session, "get", get)
    with pytest.raises(UpstreamUnavailableError) as caught:
        congress_gov_bills._get("bill/119/hr/1")
    assert get.call_count == 1
    assert get.call_args.kwargs["timeout"] == (10, 30)
    message = str(caught.value)
    assert "bill/119/hr/1" in message
    assert _SECRET not in message
    assert caught.value.__suppress_context__


def test_get_exhausted_server_errors_are_an_outage(
    congress_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    get = Mock(return_value=SimpleNamespace(status_code=503))
    monkeypatch.setattr(congress_gov_bills._session, "get", get)
    monkeypatch.setattr(congress_gov_bills.time, "sleep", lambda _: None)
    with pytest.raises(UpstreamUnavailableError, match="HTTP 503"):
        congress_gov_bills._get("bill/119")
    assert get.call_count == congress_gov_bills._MAX_RETRIES


def test_breaker_counts_only_consecutive_outages() -> None:
    breaker = OutageBreaker(2)
    assert not breaker.failure(_outage())
    assert not breaker.failure(RuntimeError("HTTP 404"))
    assert not breaker.failure(_outage())
    breaker.success()
    assert not breaker.failure(_outage())
    assert breaker.failure(_outage())
    with pytest.raises(ValueError):
        OutageBreaker(0)


def test_batch_result_degraded_and_detail() -> None:
    assert BatchResult(total=250, succeeded=250, failed=0).describe("bills") is None
    minor = BatchResult(total=250, succeeded=249, failed=1)
    assert not minor.degraded
    assert minor.describe("bills") == "1 of 250 bills failed"
    heavy = BatchResult(total=250, succeeded=69, failed=181)
    assert heavy.degraded
    stopped = BatchResult(total=250, succeeded=2, failed=3, stopped="down")
    assert stopped.degraded
    assert stopped.describe("bills") == (
        "3 of 250 bills failed; stopped early (down) with 245 not attempted"
    )


def _bills_listing(monkeypatch: pytest.MonkeyPatch, count: int) -> None:
    items = [SimpleNamespace(type="HR", number=n) for n in range(1, count + 1)]
    monkeypatch.setattr(congress_gov_bills, "_bill_list", lambda congress, cap: items)


def test_bills_run_stops_on_outage_without_staging(
    congress_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bills_listing(monkeypatch, 250)
    fetch = Mock(side_effect=_outage())
    stage = Mock()
    monkeypatch.setattr(congress_gov_bills, "_fetch_one", fetch)
    monkeypatch.setattr(congress_gov_bills, "_stage", stage)
    with pytest.raises(UpstreamUnavailableError, match="no bills fetched"):
        congress_gov_bills.run()
    assert fetch.call_count == 3
    stage.assert_not_called()


def test_bills_run_stages_what_it_got_before_an_outage(
    congress_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bills_listing(monkeypatch, 250)
    outcomes: list[object] = [{"bill": 1}, {"bill": 2}] + [_outage()] * 10

    def fetch(congress: int, bill_type: str, number: int) -> object:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    stage = Mock()
    monkeypatch.setattr(congress_gov_bills, "_fetch_one", fetch)
    monkeypatch.setattr(congress_gov_bills, "_stage", stage)
    result = congress_gov_bills.run()
    assert stage.call_args.args[1] == [{"bill": 1}, {"bill": 2}]
    assert (result.total, result.succeeded, result.failed) == (250, 2, 3)
    assert result.stopped is not None
    assert result.degraded


def test_bills_item_errors_do_not_trip_the_breaker(
    congress_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bills_listing(monkeypatch, 6)
    outcomes: list[object] = [
        _outage(), _outage(), RuntimeError("HTTP 404"), _outage(), _outage(), {"bill": 6},
    ]

    def fetch(congress: int, bill_type: str, number: int) -> object:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(congress_gov_bills, "_fetch_one", fetch)
    monkeypatch.setattr(congress_gov_bills, "_stage", Mock())
    result = congress_gov_bills.run()
    assert not outcomes
    assert result.stopped is None
    assert (result.succeeded, result.failed) == (1, 5)


def test_bills_run_honors_its_time_budget(
    congress_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "congress_gov_bills_max_seconds", 60)
    _bills_listing(monkeypatch, 250)
    clock = [0.0]
    monkeypatch.setattr(congress_gov_bills.time, "monotonic", lambda: clock[0])

    def slow_fetch(congress: int, bill_type: str, number: int) -> dict:
        clock[0] += 25
        return {"bill": number}

    stage = Mock()
    monkeypatch.setattr(congress_gov_bills, "_fetch_one", slow_fetch)
    monkeypatch.setattr(congress_gov_bills, "_stage", stage)
    result = congress_gov_bills.run()
    assert len(stage.call_args.args[1]) == 3
    assert result.stopped is not None and "time budget" in result.stopped


def test_sponsored_run_stages_partial_rows_on_outage(
    congress_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(congress_member_sponsored, "STAGING_DIR", tmp_path)
    monkeypatch.setattr(congress_member_sponsored, "STAGING_PATH", tmp_path / "sponsored.json")
    monkeypatch.setattr(congress_member_sponsored, "_bioguides", lambda: [f"M{i:06d}" for i in range(10)])
    outcomes: list[object] = [[{"bill_id": "hr1-119"}]] + [_outage()] * 9

    def sponsored_for(bioguide: str, congress: int) -> object:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(congress_member_sponsored, "_sponsored_for", sponsored_for)
    result = congress_member_sponsored.run()
    assert json.loads((tmp_path / "sponsored.json").read_text()) == [{"bill_id": "hr1-119"}]
    assert (result.total, result.succeeded, result.failed) == (10, 1, 3)
    assert result.stopped is not None


@pytest.fixture
def meetings_staging(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "meetings.json"
    monkeypatch.setattr(congress_committee_meetings, "STAGING_DIR", tmp_path)
    monkeypatch.setattr(congress_committee_meetings, "STAGING_PATH", path)
    monkeypatch.setattr(
        congress_committee_meetings,
        "_event_ids",
        lambda congress, chamber, cap: [f"{chamber}-{n}" for n in range(20)],
    )
    return path


def test_meetings_outage_never_stages_a_full_replace(
    congress_env: None, monkeypatch: pytest.MonkeyPatch, meetings_staging: Path
) -> None:
    detail = Mock(side_effect=_outage())
    monkeypatch.setattr(congress_committee_meetings, "_meeting_row", detail)
    with pytest.raises(UpstreamUnavailableError, match="not staged"):
        congress_committee_meetings.run()
    assert detail.call_count == 3
    assert not meetings_staging.exists()


def test_meetings_chamber_list_failure_never_stages(
    congress_env: None, monkeypatch: pytest.MonkeyPatch, meetings_staging: Path
) -> None:
    def event_ids(congress: int, chamber: str, cap: int) -> list[str]:
        if chamber == "senate":
            raise _outage()
        return ["house-1"]

    monkeypatch.setattr(congress_committee_meetings, "_event_ids", event_ids)
    monkeypatch.setattr(congress_committee_meetings, "_meeting_row", Mock(return_value={"event_id": "1"}))
    with pytest.raises(UpstreamUnavailableError):
        congress_committee_meetings.run()
    assert not meetings_staging.exists()


def test_meetings_heavy_item_failures_never_stage(
    congress_env: None, monkeypatch: pytest.MonkeyPatch, meetings_staging: Path
) -> None:
    calls = [0]

    def meeting_row(congress: int, chamber: str, event_id: str, logged: list[bool]) -> dict:
        calls[0] += 1
        if calls[0] % 2:
            raise RuntimeError("HTTP 404")
        return {"event_id": event_id}

    monkeypatch.setattr(congress_committee_meetings, "_meeting_row", meeting_row)
    with pytest.raises(RuntimeError, match="too many failures"):
        congress_committee_meetings.run()
    assert not meetings_staging.exists()


def test_meetings_healthy_run_stages(
    congress_env: None, monkeypatch: pytest.MonkeyPatch, meetings_staging: Path
) -> None:
    monkeypatch.setattr(
        congress_committee_meetings,
        "_meeting_row",
        lambda congress, chamber, event_id, logged: {"event_id": event_id},
    )
    result = congress_committee_meetings.run()
    assert len(json.loads(meetings_staging.read_text())) == 40
    assert not result.degraded


class _FakeSession:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids
        self.rollback = AsyncMock()

    async def execute(self, _statement: object) -> SimpleNamespace:
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: list(self._ids)))

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def test_backfill_stops_on_outage(congress_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = [f"hr{n}-119" for n in range(200)]
    monkeypatch.setattr(bill_enrich, "async_session_factory", lambda: _FakeSession(ids))
    enrich = AsyncMock(side_effect=_outage())
    monkeypatch.setattr(bill_enrich, "enrich_bill", enrich)
    with pytest.raises(UpstreamUnavailableError, match="backfill enriched nothing"):
        asyncio.run(bill_enrich.backfill_unenriched(200))
    assert enrich.await_count == 3
    assert enrich.await_args.kwargs == {"raise_unavailable": True}


def test_public_enrichment_stays_fail_soft_during_outage(
    congress_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bill_enrich, "run_upstream", AsyncMock(side_effect=_outage()))
    db = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(enriched_at=None)))
    assert asyncio.run(bill_enrich.enrich_bill(db, "hr1-119")) is False
    with pytest.raises(UpstreamUnavailableError):
        asyncio.run(bill_enrich.enrich_bill(db, "hr1-119", raise_unavailable=True))


def test_outages_are_not_retried_but_other_failures_are() -> None:
    outage = AsyncMock(side_effect=_outage())
    assert asyncio.run(refresh._run_with_retry("bills", outage, delay=0)) is False
    assert outage.await_count == 1
    flaky = AsyncMock(side_effect=RuntimeError("db blip"))
    assert asyncio.run(refresh._run_with_retry("bills", flaky, delay=0)) is False
    assert flaky.await_count == 3


@pytest.mark.parametrize(
    ("result", "status"),
    [
        (BatchResult(total=250, succeeded=69, failed=5, stopped="upstream down"), "partial"),
        (BatchResult(total=250, succeeded=249, failed=1), "ok"),
    ],
)
def test_refresh_bills_records_degraded_runs_as_partial(
    monkeypatch: pytest.MonkeyPatch, result: BatchResult, status: str
) -> None:
    monkeypatch.setattr(congress_gov_bills, "run", lambda: result)
    monkeypatch.setattr(refresh, "normalize_bills", AsyncMock(return_value=result.succeeded))
    record = AsyncMock()
    monkeypatch.setattr(refresh, "record_run", record)
    asyncio.run(refresh.refresh_bills())
    record.assert_awaited_once_with(
        "congress_gov_bills", result.succeeded, status, result.describe("bills")
    )
