"""Map between our committee_id and Congress.gov's `systemCode`.

Our committee_id is the unitedstates/congress-legislators THOMAS id: a 4-char
parent code (House Agriculture = ``HSAG``) or parent+2-digit for a subcommittee
(``HSAG14``). Congress.gov codes the *full* committee as the 4-letter stem + a
``00`` suffix (``hsag00``) and a subcommittee as the stem + its 2-digit code
(``hsag14``). The two therefore map deterministically, in both directions — no
extra lookup table needed. Callers still validate a derived committee_id against
the committees we actually hold (dropping anything unknown).
"""

from __future__ import annotations


def to_system_code(committee_id: str) -> str:
    """`HSAG` -> `hsag00`; `HSAG14` -> `hsag14`."""
    cid = committee_id.strip()
    if len(cid) == 4:  # a full-committee THOMAS id
        return f"{cid.lower()}00"
    return cid.lower()


def to_committee_id(system_code: str) -> str:
    """`hsag00` -> `HSAG` (full committee); `hsag14` -> `HSAG14` (subcommittee)."""
    sc = system_code.strip().lower()
    if sc.endswith("00"):
        return sc[:-2].upper()
    return sc.upper()
