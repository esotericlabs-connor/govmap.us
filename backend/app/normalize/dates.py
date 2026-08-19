"""Shared date/datetime normalization for the Layer 2 normalizers.

AGENTS.md rule: every date is ISO 8601, parsed through one shared utility — never
store a raw source date string. Sources hand dates back inconsistently (a plain
"2026-07-22", a full timestamp "2026-07-22T08:09:17Z", or an already-parsed
date/datetime object), so both helpers accept any of those shapes and fail soft
to None rather than aborting a whole normalize batch on one unexpected value.
"""

from __future__ import annotations

from datetime import date, datetime


def normalize_date(value: object) -> date | None:
    """Reduce any ISO-8601 date/datetime string (or date/datetime object) to a
    plain `date`. Returns None for empty/None or an unparseable value."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def normalize_datetime(value: object) -> datetime | None:
    """Parse an ISO-8601 datetime (tolerating a trailing 'Z') to a `datetime`.
    Returns None for empty/None or an unparseable value."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
