"""Curated, sourced context for vacant congressional seats.

Whether a seat is *vacant* is derived automatically from the `members` table (a
district with no current holder) — this file never decides that. It only adds
the human context "when will it be filled", for the handful of vacant seats
where a special-election date has been confirmed and sourced.

Why a hand-maintained file instead of a pipeline: there is no single
machine-readable federal feed of special-election dates — they're set by each
state's election office. To stay true to GovMap's "sourced data only" rule,
every entry MUST cite where its date came from (a state SOS page or the Clerk of
the House). Leave a district out and its map popover shows the generic "a
special election will fill it" note; add an entry and the popover shows the
scheduled date plus the source link.

Keys use the same STATE-DISTRICT form as the map (e.g. "TX-18"); at-large = the
STATE plus "-0" (e.g. "AK-0"). Dates are ISO 8601 (YYYY-MM-DD), per the
normalization rules.

To add a confirmed vacancy, copy this template into HOUSE_VACANCIES:

    "TX-18": {
        "special_election_date": "2025-11-04",
        "note": "Special election to fill the vacant seat.",
        "source_url": "https://www.sos.state.tx.us/elections/...",
    },
"""

from __future__ import annotations

# STATE-DISTRICT -> curated context. Intentionally empty until each entry's date
# is confirmed and sourced — do not populate with unverified dates.
HOUSE_VACANCIES: dict[str, dict[str, str]] = {}


def vacancy_context(key: str) -> dict[str, str] | None:
    """Curated context for a vacant-seat key, or None if we haven't sourced one."""
    return HOUSE_VACANCIES.get(key)
