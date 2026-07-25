"""Fixed allowlist of bug-report categories → areas of the app.

A closed enum (never free text), mirrored in shape by
`frontend/lib/report-categories.ts`. Because the report endpoint validates
category/subcategory against this set and rejects anything else, those fields
can't be an injection vector — only the free-text message is scrubbed. Each
category maps to a part of the codebase so a report routes straight to the
relevant code.
"""

from __future__ import annotations

# category -> ordered subcategories (first is the default when unspecified)
REPORT_CATEGORIES: dict[str, list[str]] = {
    "Map": ["District / state map", "ZIP lookup"],
    "Members": ["Profile", "Roster", "Search"],
    "Finance": ["Campaign totals", "Itemized donations"],
    "Bills": ["Bill detail", "Full text", "Bill list"],
    "Votes": ["Vote detail", "Vote list"],
    "Committees": ["Committee detail", "Meetings", "Referred bills"],
    "Search": ["Universal search"],
    "Data accuracy": ["Wrong or missing data"],
    "Site / UI": ["Layout", "Performance", "Something else"],
    "Other": ["Other"],
}

DEFAULT_CATEGORY = "Other"


def normalize(category: str, subcategory: str) -> tuple[str, str]:
    """Coerce (category, subcategory) to a valid pair from the allowlist,
    falling back to Other / the category's first subcategory."""
    cat = category if category in REPORT_CATEGORIES else DEFAULT_CATEGORY
    subs = REPORT_CATEGORIES[cat]
    sub = subcategory if subcategory in subs else subs[0]
    return cat, sub
