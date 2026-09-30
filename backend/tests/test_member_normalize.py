"""The members Layer-2 mapping: chamber/district canonicalization, the
"in office since" contiguity walk, the party backfill, and the derived fields
(photo URL, FEC id array, name fallback). These are the joins/derivations that
would corrupt member data silently if they drifted.
"""

from collections.abc import Callable
from datetime import date

from app.normalize.members import current_term, resolve_party, served_since, to_member_row
from app.schemas.member import LegislatorRaw


def _leg(rec: dict) -> LegislatorRaw:
    return LegislatorRaw.model_validate(rec)


def test_house_chamber_and_district_mapping(
    legislator: Callable[..., dict], term: Callable[..., dict]
):
    row = to_member_row(_leg(legislator(terms=[term(type_="rep", state="TX", district=23)])))
    assert row["chamber"] == "house"
    assert row["state"] == "TX"
    assert row["district"] == 23


def test_senate_district_is_none(
    legislator: Callable[..., dict], term: Callable[..., dict]
):
    row = to_member_row(_leg(legislator(terms=[term(type_="sen", state="WA", district=None)])))
    assert row["chamber"] == "senate"
    assert row["district"] is None


def test_photo_url_derived_from_bioguide(legislator: Callable[..., dict]):
    row = to_member_row(_leg(legislator(bioguide="C000127")))
    assert row["photo_url"].endswith("/C000127.jpg")


def test_official_full_name_prefers_official(legislator: Callable[..., dict]):
    row = to_member_row(_leg(legislator(first="Maria", last="Cantwell", official_full="Maria E. Cantwell")))
    assert row["official_full_name"] == "Maria E. Cantwell"


def test_official_full_name_falls_back_to_first_last(legislator: Callable[..., dict]):
    row = to_member_row(_leg(legislator(first="Ada", last="Adams", official_full=None)))
    assert row["official_full_name"] == "Ada Adams"


def test_fec_candidate_ids_stored_as_list(legislator: Callable[..., dict]):
    # AGENTS.md: FEC candidate ids are an array (members get new ids per cycle).
    row = to_member_row(_leg(legislator(fec=["H0WA05123", "S8WA00456"])))
    assert row["fec_candidate_ids"] == ["H0WA05123", "S8WA00456"]


def test_served_since_single_term(
    legislator: Callable[..., dict], term: Callable[..., dict]
):
    leg = _leg(legislator(terms=[term(start="2025-01-03", end="2027-01-03")]))
    assert served_since(leg) == date(2025, 1, 3)


def test_served_since_walks_contiguous_terms(
    legislator: Callable[..., dict], term: Callable[..., dict]
):
    terms = [
        term(start="2021-01-03", end="2023-01-03"),
        term(start="2023-01-03", end="2025-01-03"),
        term(start="2025-01-03", end="2027-01-03"),
    ]
    assert served_since(_leg(legislator(terms=terms))) == date(2021, 1, 3)


def test_served_since_breaks_on_multi_year_gap(
    legislator: Callable[..., dict], term: Callable[..., dict]
):
    terms = [
        term(start="2007-01-03", end="2009-01-03"),  # left, then returned later
        term(start="2025-01-03", end="2027-01-03"),
    ]
    assert served_since(_leg(legislator(terms=terms))) == date(2025, 1, 3)


def test_served_since_breaks_on_chamber_switch(
    legislator: Callable[..., dict], term: Callable[..., dict]
):
    # House stint then a continuous Senate tenure (Cantwell-style) → 2001, the
    # Senate start, not the earlier House term.
    terms = [
        term(type_="rep", start="1993-01-03", end="1995-01-03", state="WA", district=1),
        term(type_="sen", start="2001-01-03", end="2007-01-03", state="WA", district=None),
        term(type_="sen", start="2007-01-03", end="2013-01-03", state="WA", district=None),
        term(type_="sen", start="2013-01-03", end="2019-01-03", state="WA", district=None),
        term(type_="sen", start="2019-01-03", end="2025-01-03", state="WA", district=None),
    ]
    assert served_since(_leg(legislator(terms=terms))) == date(2001, 1, 3)


def test_resolve_party_uses_current_term(
    legislator: Callable[..., dict], term: Callable[..., dict]
):
    leg = _leg(legislator(terms=[term(party="Republican")]))
    assert resolve_party(leg, current_term(leg)) == "Republican"


def test_resolve_party_backfills_from_history(
    legislator: Callable[..., dict], term: Callable[..., dict]
):
    terms = [
        term(party="Democrat", start="2021-01-03", end="2023-01-03"),
        term(party=None, start="2023-01-03", end="2025-01-03"),
    ]
    leg = _leg(legislator(terms=terms))
    assert resolve_party(leg, current_term(leg)) == "Democrat"


def test_resolve_party_unknown_when_never_set(
    legislator: Callable[..., dict], term: Callable[..., dict]
):
    leg = _leg(legislator(terms=[term(party=None)]))
    assert resolve_party(leg, current_term(leg)) == "Unknown"
