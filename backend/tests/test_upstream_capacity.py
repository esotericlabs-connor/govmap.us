import asyncio
import json
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.config import settings
from app.main import upstream_capacity_handler
from app.pipelines import congress_gov_bills, fec_finance
from app.routers import bills
from app.routers import donations as donation_routes
from app.services import bill_enrich, committees, donations, upstream
from app.services.upstream import UpstreamCapacityError, _Budget


class _Response:
    def __init__(self, status_code: int, body: bytes = b"") -> None:
        self.status_code = status_code
        self._body = body
        self.headers: dict[str, str] = {}
        self.raw = None

    def iter_content(self, chunk_size: int = 1) -> Iterator[bytes]:
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def close(self) -> None:
        pass


def test_hourly_attempt_limit_and_exact_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    monkeypatch.setattr(upstream.time, "monotonic", lambda: clock[0])
    budget = _Budget("fec", 2, 2)
    for _ in range(2):
        with budget.slot():
            pass
    with pytest.raises(UpstreamCapacityError) as caught:
        with budget.slot():
            pytest.fail("exhausted budget admitted a request")
    assert caught.value.retry_after == 3600
    clock[0] = 3599.0
    with pytest.raises(UpstreamCapacityError) as caught:
        with budget.slot():
            pytest.fail("budget expired early")
    assert caught.value.retry_after == 1
    clock[0] = 3600.0
    with budget.slot():
        pass


def test_concurrency_limit_releases_after_failure() -> None:
    budget = _Budget("fec", 10, 1)
    with pytest.raises(RuntimeError, match="worker failed"):
        with budget.slot():
            with pytest.raises(UpstreamCapacityError) as caught:
                with budget.slot():
                    pytest.fail("concurrency limit exceeded")
            assert caught.value.retry_after == 1
            raise RuntimeError("worker failed")
    with budget.slot():
        pass


def test_hourly_limit_is_atomic_across_threads() -> None:
    budget = _Budget("fec", 3, 16)
    barrier = threading.Barrier(16)

    def attempt() -> bool:
        barrier.wait(timeout=5)
        try:
            with budget.slot():
                return True
        except UpstreamCapacityError:
            return False

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(attempt) for _ in range(16)]
        assert sum(f.result(timeout=5) for f in futures) == 3


def test_pipeline_and_public_fec_requests_share_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(upstream._BUDGETS, "fec", _Budget("fec", 1, 1))
    response = _Response(200, b'{"results": []}')
    pipeline_get = Mock(return_value=response)
    public_get = Mock(return_value=response)
    monkeypatch.setattr(fec_finance._session, "get", pipeline_get)
    monkeypatch.setattr(donations._session, "get", public_get)
    assert fec_finance._fec_get("candidate/test/totals") == {"results": []}
    with pytest.raises(UpstreamCapacityError):
        donations._fec_get("schedules/schedule_a")
    assert pipeline_get.call_count == 1
    public_get.assert_not_called()


def test_retry_consumes_budget_before_another_http_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(upstream._BUDGETS, "congress", _Budget("congress", 1, 1))
    get = Mock(return_value=_Response(503))
    monkeypatch.setattr(congress_gov_bills._session, "get", get)
    monkeypatch.setattr(congress_gov_bills.time, "sleep", lambda _: None)
    with pytest.raises(UpstreamCapacityError):
        congress_gov_bills._get("bill/119")
    assert get.call_count == 1


def test_capacity_handler_returns_explicit_503_and_retry_after() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/api/bills", "headers": []})
    response = asyncio.run(upstream_capacity_handler(request, UpstreamCapacityError("congress", 42)))
    assert response.status_code == 503
    assert response.headers["retry-after"] == "42"
    assert "capacity exhausted" in json.loads(response.body)["detail"]


def test_bill_router_does_not_swallow_capacity_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enrich = AsyncMock(side_effect=UpstreamCapacityError("congress", 10))
    db = SimpleNamespace(rollback=AsyncMock(), execute=AsyncMock())
    monkeypatch.setattr(bills, "enrich_bill", enrich)
    with pytest.raises(UpstreamCapacityError):
        asyncio.run(bills.bill_detail("hr1-119", db))
    db.rollback.assert_not_called()
    db.execute.assert_not_called()


def test_donation_page_fetch_does_not_commit_capacity_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch = AsyncMock(side_effect=UpstreamCapacityError("fec", 10))
    monkeypatch.setattr(donations, "run_upstream", fetch)
    state = SimpleNamespace(
        committee_id="C00000001",
        complete=False,
        fetched_count=0,
        cursor_index=None,
        cursor_amount=None,
    )
    db = SimpleNamespace(commit=AsyncMock())
    with pytest.raises(UpstreamCapacityError):
        asyncio.run(donations._fetch_more(db, state, 2026, 50))
    db.commit.assert_not_called()


def test_text_and_referral_services_preserve_capacity_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "congress_gov_api_key", "test-placeholder")
    fetch = AsyncMock(side_effect=UpstreamCapacityError("congress", 10))
    monkeypatch.setattr(bill_enrich, "run_upstream", fetch)
    monkeypatch.setattr(committees, "run_upstream", fetch)
    bill_db = SimpleNamespace(
        get=AsyncMock(side_effect=[None, SimpleNamespace(bill_id="hr1-119")]),
        commit=AsyncMock(),
    )
    committee_db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(first=lambda: SimpleNamespace(chamber="house"))),
        commit=AsyncMock(),
    )
    with pytest.raises(UpstreamCapacityError):
        asyncio.run(bill_enrich.get_bill_text(bill_db, "hr1-119"))
    with pytest.raises(UpstreamCapacityError):
        asyncio.run(committees.referred_bills(committee_db, "HSAG"))
    # Each service ended its read transaction before the upstream call.
    bill_db.commit.assert_awaited_once()
    committee_db.commit.assert_awaited_once()


@pytest.mark.parametrize("cycle", [2025, 2028])
def test_donation_cycle_rejected_before_database_access(
    monkeypatch: pytest.MonkeyPatch, cycle: int
) -> None:
    monkeypatch.setattr(settings, "fec_cycle", 2026)
    db = SimpleNamespace(get=AsyncMock())
    with pytest.raises(HTTPException) as caught:
        asyncio.run(donation_routes.member_donations("A000001", db, cycle=cycle))
    assert caught.value.status_code == 422
    db.get.assert_not_called()


def test_unknown_member_rejected_before_cache_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "fec_cycle", 2026)
    db = SimpleNamespace(get=AsyncMock(return_value=None))
    ledger = AsyncMock()
    monkeypatch.setattr(donation_routes, "get_donations", ledger)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(donation_routes.member_donations("A000001", db, cycle=2026))
    assert caught.value.status_code == 404
    ledger.assert_not_called()


def test_cancellation_holds_public_capacity_until_worker_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upstream, "_PUBLIC_OPERATIONS", threading.BoundedSemaphore(1))
    started = threading.Event()
    finish = threading.Event()

    def worker() -> int:
        started.set()
        if not finish.wait(timeout=5):
            raise RuntimeError("test worker was not released")
        return 7

    async def scenario() -> None:
        task = asyncio.create_task(upstream.run_upstream("fec", worker))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(UpstreamCapacityError):
                await upstream.run_upstream("fec", lambda: 8)
        finally:
            finish.set()
            remaining = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            await asyncio.gather(*remaining, return_exceptions=True)
        assert await upstream.run_upstream("fec", lambda: 8) == 8

    asyncio.run(scenario())
