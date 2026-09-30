"""Shared builders for the normalization tests.

They construct the raw congress-legislators JSON shape (exactly as the
congress_legislators pipeline stages it) so the pure Layer-2 helpers can be
exercised without a database or a live pull.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest


def _term(
    type_: str = "rep",
    start: str = "2023-01-03",
    end: str = "2025-01-03",
    state: str = "WA",
    district: int | None = 7,
    party: str | None = "Democrat",
    **extra: object,
) -> dict:
    t: dict = {"type": type_, "start": start, "end": end, "state": state, "party": party}
    if district is not None:
        t["district"] = district
    t.update(extra)
    return t


def _legislator(
    bioguide: str = "A000001",
    first: str = "Ada",
    last: str = "Adams",
    official_full: str | None = None,
    fec: list[str] | None = None,
    terms: list[dict] | None = None,
    bio: dict | None = None,
) -> dict:
    rec: dict = {
        "id": {"bioguide": bioguide, "fec": fec or []},
        "name": {"first": first, "last": last},
        "terms": terms if terms is not None else [_term()],
    }
    if official_full is not None:
        rec["name"]["official_full"] = official_full
    if bio is not None:
        rec["bio"] = bio
    return rec


@pytest.fixture
def term() -> Callable[..., dict]:
    return _term


@pytest.fixture
def legislator() -> Callable[..., dict]:
    return _legislator
