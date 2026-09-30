"""The LegislatorRaw term-resilience validator — the code behind the
"Vacant / no data" seat bug. It must drop only the individual malformed terms so
one bad historical term can never knock a sitting member off the map, yet still
reject a record whose terms are entirely unusable.
"""

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.schemas.member import LegislatorRaw


def test_malformed_historical_term_dropped_current_seat_survives(
    legislator: Callable[..., dict], term: Callable[..., dict]
):
    good = term(state="TX", district=23, start="2023-01-03", end="2025-01-03")
    current = term(state="TX", district=23, start="2025-01-03", end="2027-01-03")
    bad = {"type": "rep", "end": "2019-01-03", "state": "TX"}  # missing required start
    leg = LegislatorRaw.model_validate(legislator(terms=[bad, good, current]))
    assert len(leg.terms) == 2
    assert leg.terms[-1].district == 23  # the sitting rep's seat is intact


def test_all_terms_malformed_record_rejected(legislator: Callable[..., dict]):
    bad = {"type": "gov", "start": "2019-01-03", "end": "2021-01-03", "state": "XX"}
    with pytest.raises(ValidationError):
        LegislatorRaw.model_validate(legislator(terms=[bad]))


def test_empty_terms_rejected(legislator: Callable[..., dict]):
    with pytest.raises(ValidationError):
        LegislatorRaw.model_validate(legislator(terms=[]))


def test_null_party_on_current_term_survives(
    legislator: Callable[..., dict], term: Callable[..., dict]
):
    # congress-legislators writes party: null on a freshly added term; requiring
    # it would drop the member's real current term (the original vacancy bug).
    leg = LegislatorRaw.model_validate(
        legislator(terms=[term(party=None, state="WA", district=7)])
    )
    assert leg.terms[-1].party is None
