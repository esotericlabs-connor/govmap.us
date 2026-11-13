"""End-to-end ASGI checks: real requests through FastAPI's middleware stack,
routing, body parsing and exception handling, without a server or httpx. Unit
tests elsewhere call route functions directly, so these are what catch a
FastAPI/Starlette incompatibility or a mis-wired middleware."""

import asyncio
import base64
import json
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from pydantic import BaseModel
from sqlalchemy.dialects import postgresql
from starlette.types import ASGIApp, Message

from app import main
from app.body_limit import MAX_REQUEST_BODY_BYTES, BodySizeLimitMiddleware
from app.config import settings
from app.db import get_db
from app.models.source_run import SourceRun
from app.routers import report
from app.services.upstream import (
    UpstreamBudgetInitializingError,
    UpstreamBudgetUnavailableError,
    UpstreamCapacityError,
)


async def _call(
    app: ASGIApp,
    method: str,
    path: str,
    *,
    query: str = "",
    chunks: Sequence[bytes] = (),
    headers: Sequence[tuple[str, str]] = (),
) -> tuple[int, dict[str, str], bytes]:
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "root_path": "",
        "query_string": query.encode("ascii"),
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in headers
        ],
        "client": ("198.51.100.20", 50000),
        "server": ("testserver", 80),
    }
    pending: list[Message] = [
        {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
        for i, chunk in enumerate(chunks)
    ] or [{"type": "http.request", "body": b"", "more_body": False}]
    done = asyncio.Event()
    sent: list[Message] = []

    async def receive() -> Message:
        if pending:
            return pending.pop(0)
        await done.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body"):
            done.set()

    await asyncio.wait_for(app(scope, receive, send), timeout=10)
    start = next(m for m in sent if m["type"] == "http.response.start")
    response_headers = {
        name.decode("latin-1"): value.decode("latin-1")
        for name, value in start.get("headers", [])
    }
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], response_headers, body


class _Echo(BaseModel):
    text: str


def _echo_app(calls: list[str], max_bytes: int = 32) -> FastAPI:
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_bytes)

    @app.post("/echo")
    async def echo(payload: _Echo) -> dict[str, str]:
        calls.append(payload.text)
        return {"text": payload.text}

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    return app


_JSON = ("content-type", "application/json")


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (
            UpstreamCapacityError("congress", 42),
            "Upstream request capacity exhausted; try again later",
        ),
        (
            UpstreamBudgetInitializingError("congress", 3600),
            "Upstream request budget initializing; wait for the one-hour rollout hold",
        ),
        (
            UpstreamBudgetUnavailableError("congress", 5),
            "Upstream shared request budget unavailable; try again later",
        ),
    ],
)
def test_budget_errors_use_the_registered_handler_and_never_expose_exception_text(
    error: UpstreamCapacityError, detail: str,
) -> None:
    app = FastAPI(exception_handlers=main.app.exception_handlers)
    error.args = ("private-placeholder",)

    @app.get("/probe")
    async def probe() -> None:
        raise error

    status, headers, body = asyncio.run(_call(app, "GET", "/probe"))
    assert status == 503
    assert headers["retry-after"] == str(error.retry_after)
    assert json.loads(body) == {"detail": detail}
    assert b"private-placeholder" not in body


def test_body_within_limit_reaches_route() -> None:
    calls: list[str] = []
    body = b'{"text": "hi"}'
    status, _, payload = asyncio.run(
        _call(
            _echo_app(calls),
            "POST",
            "/echo",
            chunks=[body],
            headers=[_JSON, ("content-length", str(len(body)))],
        )
    )
    assert status == 200
    assert json.loads(payload) == {"text": "hi"}
    assert calls == ["hi"]


def test_declared_oversized_body_is_refused_before_the_app_runs() -> None:
    calls: list[str] = []
    body = b'{"text": "' + b"x" * 64 + b'"}'
    status, _, payload = asyncio.run(
        _call(
            _echo_app(calls),
            "POST",
            "/echo",
            chunks=[body],
            headers=[_JSON, ("content-length", str(len(body)))],
        )
    )
    assert status == 413
    assert json.loads(payload) == {"detail": "request body too large"}
    assert calls == []


def test_undeclared_streamed_body_is_cut_off_at_the_limit() -> None:
    calls: list[str] = []
    chunks = [b'{"text": "', b"x" * 20, b"x" * 20, b'"}']
    status, _, payload = asyncio.run(
        _call(_echo_app(calls), "POST", "/echo", chunks=chunks, headers=[_JSON])
    )
    assert status == 413
    assert json.loads(payload) == {"detail": "request body too large"}
    assert calls == []


def test_bodiless_requests_are_unaffected() -> None:
    status, _, payload = asyncio.run(_call(_echo_app([]), "GET", "/ping"))
    assert status == 200
    assert json.loads(payload) == {"ok": True}


@pytest.fixture
def report_sink(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    written: list[str] = []
    monkeypatch.setattr(report, "_append", written.append)
    monkeypatch.setattr(settings, "cors_origins", "")
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    report._rate.clear()
    report._global_rate.clear()
    yield written
    report._rate.clear()
    report._global_rate.clear()


def test_app_health_is_served_through_the_full_stack() -> None:
    status, headers, payload = asyncio.run(_call(main.app, "GET", "/health"))
    assert status == 200
    assert headers.get("cache-control") == "no-store"
    assert json.loads(payload)["status"] == "ok"


def test_app_accepts_a_normal_report(report_sink: list[str]) -> None:
    body = json.dumps(
        {"category": "Other", "subcategory": "Other", "message": "Broken link"}
    ).encode()
    status, _, payload = asyncio.run(
        _call(
            main.app,
            "POST",
            "/api/report",
            chunks=[body],
            headers=[_JSON, ("content-length", str(len(body)))],
        )
    )
    assert status == 200
    assert json.loads(payload) == {"ok": True}
    assert len(report_sink) == 1
    assert "Broken link" in report_sink[0]


def test_app_refuses_oversized_report_bodies(report_sink: list[str]) -> None:
    oversized = MAX_REQUEST_BODY_BYTES + 1
    declared = asyncio.run(
        _call(
            main.app,
            "POST",
            "/api/report",
            chunks=[b"x" * oversized],
            headers=[_JSON, ("content-length", str(oversized))],
        )
    )
    streamed = asyncio.run(
        _call(
            main.app,
            "POST",
            "/api/report",
            chunks=[b'{"message": "', b"x" * MAX_REQUEST_BODY_BYTES, b'"}'],
            headers=[_JSON],
        )
    )
    assert declared[0] == 413
    assert streamed[0] == 413
    assert report_sink == []


# --- internal endpoints ---------------------------------------------------------

_OPERATOR = "operator"
_OPERATOR_SECRET = "example-password"


def _basic(user: str, secret: str) -> tuple[str, str]:
    token = base64.b64encode(f"{user}:{secret}".encode()).decode("ascii")
    return ("authorization", f"Basic {token}")


@dataclass
class _FakeRunStore:
    """Stands in for the database session; records every statement it runs."""

    rows: list[SourceRun] = field(default_factory=list)
    statements: list[Any] = field(default_factory=list)

    async def execute(self, statement: Any) -> Mock:
        self.statements.append(statement)
        result = Mock()
        result.scalars.return_value.all.return_value = self.rows
        return result


@pytest.fixture
def run_store(monkeypatch: pytest.MonkeyPatch) -> Iterator[_FakeRunStore]:
    monkeypatch.setattr(settings, "internal_user", _OPERATOR)
    monkeypatch.setattr(settings, "internal_password", _OPERATOR_SECRET)
    store = _FakeRunStore()

    async def fake_db() -> AsyncIterator[_FakeRunStore]:
        yield store

    main.app.dependency_overrides[get_db] = fake_db
    try:
        yield store
    finally:
        main.app.dependency_overrides.pop(get_db, None)


def test_every_internal_route_requires_credentials(run_store: _FakeRunStore) -> None:
    paths = {
        context.path
        for context in iter_route_contexts(main.app.routes)
        if context.path and context.path.startswith("/internal")
    }
    assert {"/internal/pipeline-status", "/internal/source-runs"} <= paths
    for path in sorted(paths):
        for headers in ([], [_basic(_OPERATOR, "wrong")]):
            status, response_headers, _ = asyncio.run(
                _call(main.app, "GET", path, headers=headers)
            )
            assert status == 401, path
            assert response_headers.get("www-authenticate") == "Basic"
    assert run_store.statements == []


def test_source_runs_checks_credentials_before_filters(run_store: _FakeRunStore) -> None:
    # Bad credentials get the same 401 whatever the filters, so an
    # unauthenticated caller can't probe which source names are registered.
    status, _, _ = asyncio.run(
        _call(
            main.app,
            "GET",
            "/internal/source-runs",
            query="source=not_a_source&limit=0",
            headers=[_basic(_OPERATOR, "wrong")],
        )
    )
    assert status == 401
    assert run_store.statements == []


@pytest.mark.parametrize(
    "query",
    [
        "source=not_a_source",
        "outcome=done",
        "limit=0",
        "limit=501",
        "limit=ten",
        "before_id=0",
        "before_id=-5",
        "before_id=9223372036854775808",
        "sources=votes",
    ],
)
def test_source_runs_rejects_invalid_filters_before_querying(
    run_store: _FakeRunStore, query: str
) -> None:
    status, _, payload = asyncio.run(
        _call(
            main.app,
            "GET",
            "/internal/source-runs",
            query=query,
            headers=[_basic(_OPERATOR, _OPERATOR_SECRET)],
        )
    )
    assert status == 422
    assert json.loads(payload)["detail"]
    assert run_store.statements == []


@pytest.mark.parametrize(
    ("path", "query"),
    [
        ("/api/bills", "offset=-1"),
        ("/api/bills", "offset=1000001"),
        ("/api/bills", "offset=9223372036854775808"),
        ("/api/bills", "limit=0"),
        ("/api/bills", "limit=-1"),
        ("/api/bills", "congress=-1"),
        ("/api/bills", "congress=2147483648"),
        ("/api/bills", "status=passed_house"),
        ("/api/bills", "status=Became%20Law"),
        ("/api/votes", "offset=-1"),
        ("/api/votes", "limit=0"),
        ("/api/votes", "session=2147483648"),
        ("/api/members", "offset=-1"),
        ("/api/members", "limit=-1"),
        ("/api/members/A000360/donations", "offset=1000001"),
        ("/api/overview", "weeks=3"),
        ("/api/overview", "weeks=53"),
        ("/api/overview", "weeks=ten"),
    ],
)
def test_public_lists_reject_out_of_range_paging_before_querying(
    run_store: _FakeRunStore, path: str, query: str
) -> None:
    # PostgreSQL rejects negative LIMIT/OFFSET and out-of-range integers at
    # execution time; these must be a 422 here rather than a database 500.
    status, _, payload = asyncio.run(_call(main.app, "GET", path, query=query))
    assert status == 422
    assert json.loads(payload)["detail"]
    assert run_store.statements == []


def test_public_list_accepts_paging_bounds(run_store: _FakeRunStore) -> None:
    status, _, payload = asyncio.run(
        _call(main.app, "GET", "/api/bills", query="offset=1000000&limit=1&congress=0")
    )
    assert status == 200
    assert json.loads(payload) == []
    assert len(run_store.statements) == 1


@pytest.mark.parametrize(
    "query",
    [
        "cycle=2025",
        "cycle=2100",
        "office=X",
        "state=California",
        "office=S&state=CA&district=01",
        "office=H&district=01",
        "through=2026-02-30",
        "offset=1000001",
    ],
)
def test_money_filters_are_rejected_before_querying_data(query: str) -> None:
    status, _, _ = asyncio.run(_call(main.app, "GET", "/api/money/candidates", query=query))
    assert status == 422


def test_money_candidate_identifier_is_validated() -> None:
    status, _, _ = asyncio.run(_call(main.app, "GET", "/api/money/candidates/not-an-id"))
    assert status == 422


@pytest.mark.parametrize(("resource", "query"), [("calendar", "year=2026"), ("candidates", "cycle=2026")])
@pytest.mark.parametrize("available", [False, True])
def test_election_responses_include_utc_generation_time(
    monkeypatch: pytest.MonkeyPatch, resource: str, query: str, available: bool
) -> None:
    fetched_at = datetime(2026, 1, 3, tzinfo=UTC)
    coverage = (
        SimpleNamespace(
            complete=True,
            event_count=1,
            candidate_count=1,
            expected_count=1,
            fetched_at=fetched_at,
        )
        if available
        else None
    )
    coverage_result = Mock()
    coverage_result.scalar_one_or_none.return_value = coverage
    results = [coverage_result]

    if available and resource == "calendar":
        events = Mock()
        events.scalars.return_value.all.return_value = [
            SimpleNamespace(
                calendar_year=2026,
                event_id=1,
                category="Election Dates",
                summary="General Election",
                description=None,
                location="California",
                state=[],
                start_date=date(2026, 11, 3),
                end_date=None,
                end_date_normalized=True,
                url=None,
            )
        ]
        results.append(events)
    elif available:
        count = Mock()
        count.scalar_one.return_value = 1
        groupings = Mock()
        groupings.all.return_value = [
            SimpleNamespace(
                office="H",
                office_full="House",
                state="CA",
                district="01",
                candidate_count=1,
            )
        ]
        candidates = Mock()
        candidates.scalars.return_value.all.return_value = [
            SimpleNamespace(
                candidate_id="H0CA00001",
                finance_cycle=2026,
                name="Example Candidate",
                office="H",
                office_full="House",
                state="CA",
                district="01",
                party="DEM",
                party_full="Democratic Party",
                candidate_status="C",
                incumbent_challenge="C",
                first_file_date=None,
                last_file_date=None,
                cycles=[2026],
                election_years=[2026],
                principal_committees=[],
            )
        ]
        results.extend([count, groupings, candidates])

    db = SimpleNamespace(
        connection=AsyncMock(), execute=AsyncMock(side_effect=results)
    )

    async def fake_db() -> AsyncIterator[SimpleNamespace]:
        yield db

    monkeypatch.setitem(main.app.dependency_overrides, get_db, fake_db)
    before = datetime.now(UTC)
    status, _, body = asyncio.run(
        _call(main.app, "GET", f"/api/elections/{resource}", query=query)
    )
    after = datetime.now(UTC)

    assert status == 200
    payload = json.loads(body)
    generated_at = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
    assert generated_at.utcoffset() == timedelta(0)
    assert before <= generated_at <= after
    assert payload["available"] is available
    assert payload["complete"] is available
    items = payload["events" if resource == "calendar" else "candidates"]
    assert len(items) == int(available)
    if available:
        assert datetime.fromisoformat(payload["fetched_at"].replace("Z", "+00:00")) == fetched_at
        assert items[0]["event_id" if resource == "calendar" else "candidate_id"] == (
            1 if resource == "calendar" else "H0CA00001"
        )
    else:
        assert payload["fetched_at"] is None
    db.connection.assert_awaited_once_with(
        execution_options={"isolation_level": "REPEATABLE READ"}
    )
    assert db.execute.await_count == len(results)


@pytest.mark.parametrize("normalized", [False, True])
def test_calendar_withholds_uninterpreted_stored_end_dates(
    monkeypatch: pytest.MonkeyPatch, normalized: bool
) -> None:
    coverage = Mock()
    coverage.scalar_one_or_none.return_value = SimpleNamespace(
        complete=True,
        event_count=1,
        expected_count=1,
        fetched_at=datetime(2026, 1, 3, tzinfo=UTC),
    )
    events = Mock()
    events.scalars.return_value.all.return_value = [
        SimpleNamespace(
            calendar_year=2026,
            event_id=1,
            category="Election Dates",
            summary="Election",
            description=None,
            location=None,
            state=[],
            start_date=date(2026, 11, 3),
            end_date=date(2026, 11, 4),
            end_date_normalized=normalized,
            url=None,
        )
    ]
    db = SimpleNamespace(
        connection=AsyncMock(), execute=AsyncMock(side_effect=[coverage, events])
    )

    async def fake_db() -> AsyncIterator[SimpleNamespace]:
        yield db

    monkeypatch.setitem(main.app.dependency_overrides, get_db, fake_db)
    status, _, body = asyncio.run(
        _call(main.app, "GET", "/api/elections/calendar", query="year=2026")
    )

    assert status == 200
    event = json.loads(body)["events"][0]
    assert event["start_date"] == "2026-11-03"
    assert event["end_date_normalized"] is normalized
    assert event["end_date"] == ("2026-11-04" if normalized else None)


def test_bill_list_applies_the_became_law_filter(run_store: _FakeRunStore) -> None:
    status, _, payload = asyncio.run(
        _call(main.app, "GET", "/api/bills", query="status=became_law")
    )
    assert status == 200
    assert json.loads(payload) == []
    (statement,) = run_store.statements
    assert "bills.status = " in str(statement)


def test_source_runs_returns_filtered_history_newest_first(run_store: _FakeRunStore) -> None:
    run_store.rows.append(
        SourceRun(
            id=9,
            source="votes",
            trigger="schedule",
            code_version="a" * 40,
            started_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            finished_at=None,
            outcome="partial",
            record_count=12,
            items_total=3,
            items_succeeded=2,
            items_failed=1,
            inputs=None,
            detail="senate fallback",
        )
    )
    status, _, payload = asyncio.run(
        _call(
            main.app,
            "GET",
            "/internal/source-runs",
            query="source=votes&outcome=partial&before_id=10&limit=2",
            headers=[_basic(_OPERATOR, _OPERATOR_SECRET)],
        )
    )
    assert status == 200
    assert json.loads(payload) == [
        {
            "id": 9,
            "source": "votes",
            "trigger": "schedule",
            "code_version": "a" * 40,
            "started_at": "2026-01-02T03:04:05+00:00",
            "finished_at": None,
            "outcome": "partial",
            "record_count": 12,
            "items_total": 3,
            "items_succeeded": 2,
            "items_failed": 1,
            "inputs": None,
            "detail": "senate fallback",
        }
    ]
    (statement,) = run_store.statements
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "ORDER BY source_runs.id DESC" in str(compiled)
    assert sorted(map(str, compiled.params.values())) == ["10", "2", "partial", "votes"]
