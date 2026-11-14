import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.config import settings
from app.normalize import election_calendar
from app.normalize.dates import normalize_date
from app.pipelines import fec_election_calendar
from app.schemas.election import FecCalendarEventRaw


def _event(event_id: int = 1) -> dict:
    return {
        "all_day": True,
        "calendar_category_id": 36,
        "category": "Election Dates",
        "description": "Federal general election",
        "end_date": None,
        "event_id": event_id,
        "location": "California",
        "start_date": "2026-11-03",
        "state": None,
        "summary": "General Election",
        "url": None,
    }


def _page(events: list[dict], count: int, pages: int = 1) -> dict:
    return {
        "results": events,
        "pagination": {"count": count, "pages": pages, "is_count_exact": True},
    }


@pytest.mark.parametrize("end_date", ["2026-11-04", None])
def test_calendar_dates_use_shared_normalizer(
    monkeypatch: pytest.MonkeyPatch, end_date: str | None
) -> None:
    raw = _event()
    raw["end_date"] = end_date
    event = FecCalendarEventRaw.model_validate(raw)
    seen: list[object] = []

    def normalize_spy(value: object) -> date | None:
        seen.append(value)
        return normalize_date(value)

    monkeypatch.setattr(election_calendar, "normalize_date", normalize_spy)
    row = election_calendar._event_row(2026, event)

    assert seen == [event.start_date, event.end_date]
    assert row["start_date"] == event.start_date
    assert row["end_date"] == (date(2026, 11, 3) if end_date else None)
    assert row["end_date_normalized"] is True


def test_calendar_normalizes_timed_and_multiday_ranges() -> None:
    all_day = _event()
    all_day["end_date"] = "2026-11-06"
    all_day_row = election_calendar._event_row(2026, FecCalendarEventRaw.model_validate(all_day))
    assert all_day_row["start_date"] == date(2026, 11, 3)
    assert all_day_row["end_date"] == date(2026, 11, 5)

    timed = _event(2)
    timed["all_day"] = False
    timed["start_date"] = "2026-11-03T23:30:00-05:00"
    timed["end_date"] = "2026-11-04T00:30:00-05:00"
    timed_row = election_calendar._event_row(2026, FecCalendarEventRaw.model_validate(timed))
    assert timed_row["start_date"] == date(2026, 11, 3)
    assert timed_row["end_date"] == date(2026, 11, 4)
    assert timed_row["end_date_normalized"] is True


def test_calendar_pipeline_stages_an_exact_count_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    monkeypatch.setattr(fec_election_calendar, "STAGING_PATH", tmp_path / "calendar.json")
    requested: list[dict] = []

    def fake_get(path: str, **params: object) -> dict:
        assert path == "calendar-dates"
        requested.append(params)
        if params["page"] == 1:
            return _page([_event()], count=1)
        raise AssertionError("an additional page was not reported")

    monkeypatch.setattr(fec_election_calendar, "_fec_get", fake_get)

    result = fec_election_calendar.run(calendar_year=2026)
    staged = json.loads((tmp_path / "calendar.json").read_text(encoding="utf-8"))

    assert result.succeeded == 1
    assert staged["complete"] is True
    assert staged["expected_count"] == 1
    assert staged["page_count"] == 1
    assert staged["events"][0]["event_id"] == 1
    assert requested[0]["calendar_category_id"] == 36
    assert requested[0]["min_start_date"] == "2026-01-01"
    assert requested[0]["max_start_date"] == "2026-12-31T23:59:59.999999"
    assert requested[0]["sort"] == "event_id"


def test_calendar_pipeline_walks_all_exactly_reported_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    monkeypatch.setattr(fec_election_calendar, "STAGING_PATH", tmp_path / "calendar.json")
    monkeypatch.setattr(fec_election_calendar, "_PAGE_SIZE", 1)
    monkeypatch.setattr(fec_election_calendar, "_PAGE_PAUSE_SECONDS", 0)

    def fake_get(path: str, **params: object) -> dict:
        assert path == "calendar-dates"
        if params["page"] == 1:
            return _page([_event(1)], count=2, pages=2)
        earlier_event = _event(2)
        earlier_event["all_day"] = False
        earlier_event["start_date"] = "2026-02-01T22:30:00-05:00"
        earlier_event["end_date"] = "2026-02-02T00:30:00-05:00"
        return _page([earlier_event], count=2, pages=2)

    monkeypatch.setattr(fec_election_calendar, "_fec_get", fake_get)

    result = fec_election_calendar.run(calendar_year=2026)
    staged = json.loads((tmp_path / "calendar.json").read_text(encoding="utf-8"))

    assert result.succeeded == 2
    assert staged["page_count"] == 2
    assert [event["event_id"] for event in staged["events"]] == [2, 1]


def test_calendar_includes_timed_events_at_the_end_of_the_year(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    staging = tmp_path / "calendar.json"
    monkeypatch.setattr(fec_election_calendar, "STAGING_PATH", staging)
    event = _event()
    event["all_day"] = False
    event["start_date"] = "2026-12-31T23:59:59.999999-05:00"

    def fake_get(path: str, **params: object) -> dict:
        assert path == "calendar-dates"
        assert params["max_start_date"] == "2026-12-31T23:59:59.999999"
        return _page([event], count=1)

    monkeypatch.setattr(fec_election_calendar, "_fec_get", fake_get)
    fec_election_calendar.run(calendar_year=2026)
    assert json.loads(staging.read_text(encoding="utf-8"))["events"][0]["event_id"] == 1


def test_calendar_pipeline_rejects_invalid_exclusive_end_without_replacing_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    staging = tmp_path / "calendar.json"
    staging.write_text('{"previous":"snapshot"}', encoding="utf-8")
    monkeypatch.setattr(fec_election_calendar, "STAGING_PATH", staging)
    invalid = _event()
    invalid["end_date"] = invalid["start_date"]

    def fake_get(path: str, **params: object) -> dict:
        assert path == "calendar-dates"
        assert params["page"] == 1
        return _page([invalid], count=1)

    monkeypatch.setattr(fec_election_calendar, "_fec_get", fake_get)

    with pytest.raises(fec_election_calendar.CalendarSnapshotIncompleteError, match="invalid shape"):
        fec_election_calendar.run(calendar_year=2026)
    assert json.loads(staging.read_text(encoding="utf-8")) == {"previous": "snapshot"}


@pytest.mark.parametrize(
    "changes",
    [
        {"all_day": None},
        {"all_day": "true"},
        {
            "all_day": False,
            "start_date": "2026-11-03T23:30:00-05:00",
            "end_date": "2026-11-03T22:30:00-05:00",
        },
        {
            "all_day": False,
            "start_date": "2026-11-03T23:30:00-05:00",
            "end_date": "2026-11-04T00:30:00",
        },
    ],
)
def test_calendar_rejects_ambiguous_or_reversed_ranges(changes: dict) -> None:
    event = _event()
    event.update(changes)
    with pytest.raises(ValueError):
        FecCalendarEventRaw.model_validate(event)


def test_calendar_rejects_missing_all_day_marker() -> None:
    event = _event()
    del event["all_day"]
    with pytest.raises(ValueError):
        FecCalendarEventRaw.model_validate(event)


def test_calendar_pipeline_refuses_a_count_mismatch_without_replacing_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    staging = tmp_path / "calendar.json"
    staging.write_text('{"previous":"snapshot"}', encoding="utf-8")
    monkeypatch.setattr(fec_election_calendar, "STAGING_PATH", staging)

    def fake_get(path: str, **params: object) -> dict:
        assert path == "calendar-dates"
        assert params["page"] == 1
        return _page([_event()], 2)

    monkeypatch.setattr(
        fec_election_calendar,
        "_fec_get",
        fake_get,
    )

    with pytest.raises(
        fec_election_calendar.CalendarSnapshotIncompleteError,
        match="did not match its exact count",
    ):
        fec_election_calendar.run(calendar_year=2026)

    assert json.loads(staging.read_text(encoding="utf-8")) == {"previous": "snapshot"}


def test_calendar_pipeline_rejects_non_exact_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    monkeypatch.setattr(fec_election_calendar, "STAGING_PATH", tmp_path / "calendar.json")

    def fake_get(path: str, **_params: object) -> dict:
        assert path == "calendar-dates"
        assert _params["page"] == 1
        return {
            "results": [_event()],
            "pagination": {"count": 1, "pages": 1, "is_count_exact": False},
        }

    monkeypatch.setattr(fec_election_calendar, "_fec_get", fake_get)

    with pytest.raises(
        fec_election_calendar.CalendarSnapshotIncompleteError,
        match="did not mark the election calendar count exact",
    ):
        fec_election_calendar.run(calendar_year=2026)


def test_calendar_normalizer_refuses_incomplete_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "calendar.json"
    staging.write_text(
        json.dumps(
            {
                "source": "fec_election_calendar",
                "calendar_year": 2026,
                "complete": False,
                "expected_count": 1,
                "page_count": 1,
                "snapshot_revision": "a" * 64,
                "fetched_at": datetime.now(UTC).isoformat(),
                "events": [_event()],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(election_calendar, "STAGING_PATH", staging)

    with pytest.raises(ValueError, match="not marked complete"):
        asyncio.run(election_calendar.load_calendar())
