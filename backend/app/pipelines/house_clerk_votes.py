"""Layer 1 pipeline: House roll-call votes from the Clerk EVS XML.

Source: https://clerk.house.gov/evs/{year}/roll{NNN}.xml (root <rollcall-vote>).
House votes key each member by `name-id` = **Bioguide ID**, so positions join
`members` directly (no crosswalk needed — that's the Senate side).

Bounded + incremental: the roll numbers are sequential within a session, so we
binary-search the current maximum and pull the most-recent VOTES_LIMIT of them
(newest first). A descriptive User-Agent is REQUIRED — the Clerk 403s the
default requests UA.

The Clerk soft-404s: a missing 3-digit roll (e.g. roll999.xml) answers HTTP 200
with a tiny `<xml>Error sanitizing file ...</xml>` body (4-digit misses are a
real 404). Existence is therefore judged by the body opening a <rollcall-vote>
document, never by status alone — a status-only probe once made every 3-digit
roll "exist", converged on 999, and the run parsed nothing.

Run directly: `python -m app.pipelines.house_clerk_votes`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

from app.config import settings
from app.pipelines.staging import write_json_atomic
from app.services.bounded_http import read_body, read_prefix
from app.services.safe_parse import parse_xml

logger = logging.getLogger(__name__)

HOUSE_BASE = "https://clerk.house.gov/evs"
SOURCE_NAME = "house_clerk_votes"

STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING = STAGING_DIR / "house_votes_raw.json"

# Lead with Mozilla/5.0 (compatible; ...) — the Clerk's WAF 403s bare bot UAs
# (and the default requests UA), but honors this identifying "compatible" form.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GovMap.us/1.0; +https://govmap.us)"}
_session = requests.Session()

# A real roll file opens <rollcall-vote> within its first ~60 bytes (after the
# XML declaration); the probe reads only this much of the body.
_ROLL_ROOT = b"<rollcall-vote"
_PROBE_BYTES = 1024
_PROBE_DEADLINE_SECONDS = 20
# A roll file is about 100 KiB (one <recorded-vote> per member).
_MAX_ROLL_BYTES = 8 * 1024 * 1024
_ROLL_DEADLINE_SECONDS = 60

# House bill types map from the legis-num text (e.g. "H R 3076", "H J RES 1").
_BILL_PREFIX = {
    ("H", "R"): "hr",
    ("S", ""): "s",
    ("H", "RES"): "hres",
    ("S", "RES"): "sres",
    ("H", "J RES"): "hjres",
    ("S", "J RES"): "sjres",
    ("H", "CON RES"): "hconres",
    ("S", "CON RES"): "sconres",
}


def _year(congress: int, session: int) -> int:
    # Congress N convenes in 1789 + 2*(N-1); session 1 = that year, 2 = the next.
    return 1789 + 2 * (congress - 1) + (session - 1)


def _roll_url(year: int, n: int) -> str:
    return f"{HOUSE_BASE}/{year}/roll{n:03d}.xml"


def _int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def bill_id_from_legis(legis: str, congress: int) -> str | None:
    """"H R 3076" -> "hr3076-119"; "S 123" -> "s123-119"; "H J RES 1" ->
    "hjres1-119". Non-measure votes (QUORUM, JOURNAL, MOTION, ...) -> None."""
    parts = (legis or "").upper().replace(".", " ").split()
    if len(parts) < 2 or not parts[-1].isdigit():
        return None
    number = parts[-1]
    chamber = parts[0]
    middle = " ".join(parts[1:-1])
    prefix = _BILL_PREFIX.get((chamber, middle))
    return f"{prefix}{number}-{congress}" if prefix else None


def _is_roll_document(head: bytes) -> bool:
    return _ROLL_ROOT in head


def _exists(year: int, n: int) -> bool:
    """Only a definite missing-file response is absence, not an outage."""
    resp = _session.get(_roll_url(year, n), headers=_HEADERS, timeout=20, stream=True)
    try:
        if resp.status_code == 404:
            return False
        if resp.status_code != 200:
            raise RuntimeError(f"house clerk returned HTTP {resp.status_code} (roll {n}, {year})")
        head, _ = read_prefix(
            resp,
            max_bytes=_PROBE_BYTES,
            deadline_s=_PROBE_DEADLINE_SECONDS,
            label=f"house roll {n} probe",
        )
        if _is_roll_document(head):
            return True
        if b"Error sanitizing" in head:
            return False
        raise RuntimeError(f"house clerk returned an unexpected response (roll {n}, {year})")
    finally:
        resp.close()


def _max_roll(year: int) -> int:
    """Highest existing roll number for the year (0 if none). Roll numbers are
    gap-free and sequential, so an exponential probe + binary search finds the
    max in ~log(N) requests."""
    if not _exists(year, 1):
        return 0
    lo, hi = 1, 2
    while hi < 4096 and _exists(year, hi):
        lo, hi = hi, hi * 2
    while lo + 1 < hi:  # lo exists, hi does not
        mid = (lo + hi) // 2
        if _exists(year, mid):
            lo = mid
        else:
            hi = mid
    return lo


def _parse(root: ET.Element, year: int, congress: int, session: int) -> dict | None:
    meta = root.find("vote-metadata")
    if meta is None:
        return None
    roll = _int(meta.findtext("rollcall-num"))
    if roll is None:
        return None

    action_date = (meta.findtext("action-date") or "").strip()  # "23-Jan-2026"
    vdate = None
    try:
        vdate = datetime.strptime(action_date, "%d-%b-%Y").date().isoformat()
    except ValueError:
        pass

    totals = None
    tv = meta.find("vote-totals/totals-by-vote")
    if tv is not None:
        totals = {
            "yea": _int(tv.findtext("yea-total")),
            "nay": _int(tv.findtext("nay-total")),
            "present": _int(tv.findtext("present-total")),
            "not_voting": _int(tv.findtext("not-voting-total")),
        }

    positions = []
    for rv in root.findall("vote-data/recorded-vote"):
        leg = rv.find("legislator")
        if leg is None:
            continue
        bioguide = leg.get("name-id")
        if not bioguide:
            continue
        positions.append({"bioguide_id": bioguide, "position": (rv.findtext("vote") or "").strip()})
    if not positions:
        return None

    return {
        "vote_id": f"h{congress}-{session}-{roll}",
        "chamber": "house",
        "congress": congress,
        "session": session,
        "roll_number": roll,
        "date": vdate,
        "question": (meta.findtext("vote-question") or "").strip() or None,
        "result": (meta.findtext("vote-result") or "").strip() or None,
        "bill_id": bill_id_from_legis(meta.findtext("legis-num") or "", congress),
        "totals": totals,
        "source_url": _roll_url(year, roll),
        "positions": positions,
    }


def _stage(data) -> None:
    write_json_atomic(STAGING, data, indent=2)


def run() -> int:
    congress = settings.congress_number
    session = settings.congress_session
    year = _year(congress, session)

    top = _max_roll(year)
    if top == 0:
        _stage([])
        logger.info("house_clerk_votes: no roll calls yet for %d", year)
        return 0

    lo = max(1, top - settings.votes_limit + 1)
    staged: list[dict] = []
    for n in range(top, lo - 1, -1):  # newest first
        resp = _session.get(_roll_url(year, n), headers=_HEADERS, timeout=20, stream=True)
        try:
            if resp.status_code != 200:
                raise RuntimeError(f"house roll {n} returned HTTP {resp.status_code}")
            label = f"house roll {n}"
            body = read_body(
                resp, max_bytes=_MAX_ROLL_BYTES, deadline_s=_ROLL_DEADLINE_SECONDS, label=label
            )
            root = parse_xml(body, label=label)
            vote = _parse(root, year, congress, session) if root.tag == "rollcall-vote" else None
            if not vote or vote["roll_number"] != n:
                raise ValueError(f"house roll {n} is not a matching roll-call document")
            staged.append(vote)
        finally:
            resp.close()
    if not staged:
        raise ValueError(f"no house votes parsed (year {year}, top roll {top})")

    _stage(staged)
    logger.info("house_clerk_votes: staged %d votes (year %d, rolls %d..%d)", len(staged), year, lo, top)
    return len(staged)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
