"""The single ISO-8601 date/datetime utility every normalizer routes through
(AGENTS.md rule). A regression here silently breaks every date-range query, so
its parsing + fail-soft behavior is pinned down here.
"""

from datetime import UTC, date, datetime

from app.normalize.dates import normalize_date, normalize_datetime


def test_normalize_date_from_plain_iso():
    assert normalize_date("2026-07-22") == date(2026, 7, 22)


def test_normalize_date_from_timestamp_with_z():
    assert normalize_date("2026-07-22T08:09:17Z") == date(2026, 7, 22)


def test_normalize_date_passthrough_objects():
    assert normalize_date(date(2026, 1, 2)) == date(2026, 1, 2)
    assert normalize_date(datetime(2026, 1, 2, 3, 4)) == date(2026, 1, 2)


def test_normalize_date_none_and_empty_are_none():
    assert normalize_date(None) is None
    assert normalize_date("") is None


def test_normalize_date_unparseable_is_none():
    # Fail soft (None), never raise — one bad value can't abort a batch.
    assert normalize_date("not a date") is None
    assert normalize_date("07/22/2026") is None


def test_normalize_datetime_tolerates_z():
    assert normalize_datetime("2026-07-22T08:09:17Z") == datetime(
        2026, 7, 22, 8, 9, 17, tzinfo=UTC
    )


def test_normalize_datetime_from_date():
    assert normalize_datetime(date(2026, 1, 2)) == datetime(2026, 1, 2)


def test_normalize_datetime_unparseable_is_none():
    assert normalize_datetime("nope") is None
    assert normalize_datetime(None) is None
