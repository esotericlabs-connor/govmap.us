import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import settings
from app.normalize import election_calendar
from app.pipelines import fec_election_calendar


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
    assert requested[0]["max_start_date"] == "2026-12-31"


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
        return _page([_event(2)], count=2, pages=2)

    monkeypatch.setattr(fec_election_calendar, "_fec_get", fake_get)

    result = fec_election_calendar.run(calendar_year=2026)
    staged = json.loads((tmp_path / "calendar.json").read_text(encoding="utf-8"))

    assert result.succeeded == 2
    assert staged["page_count"] == 2
    assert [event["event_id"] for event in staged["events"]] == [1, 2]


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
