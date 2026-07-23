"""Layer 1 pipeline: House roll-call votes from the Clerk EVS XML.

Source: https://clerk.house.gov/evs/{year}/roll{NNN}.xml (root <rollcall-vote>).
House votes key each member by `name-id` = **Bioguide ID**, so positions join
`members` directly (no crosswalk needed — that's the Senate side).

Bounded + incremental: the roll numbers are sequential within a session, so we
binary-search the current maximum and pull the most-recent VOTES_LIMIT of them
(newest first). A descriptive User-Agent is REQUIRED — the Clerk 403s the
default requests UA.

Run directly: `python -m app.pipelines.house_clerk_votes`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

from app.config import settings

logger = logging.getLogger(__name__)

HOUSE_BASE = "https://clerk.house.gov/evs"
SOURCE_NAME = "house_clerk_votes"

STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING = STAGING_DIR / "house_votes_raw.json"

# Lead with Mozilla/5.0 (compatible; ...) — the Clerk's WAF 403s bare bot UAs
# (and the default requests UA), but honors this identifying "compatible" form.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GovMap.us/1.0; +https://govmap.us)"}
_session = requests.Session()

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


def _exists(year: int, n: int) -> bool:
    # Status-only probe — stream + close so we don't download the body.
    try:
        resp = _session.get(_roll_url(year, n), headers=_HEADERS, timeout=20, stream=True)
        ok = resp.status_code == 200
        resp.close()
        return ok
    except requests.RequestException:
        return False


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
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(json.dumps(data, indent=2))


def run() -> int:
    congress = settings.congress_number
    session = settings.congress_session
    year = _year(congress, session)

    # Authoritative reachability probe on roll 1: 404 = no votes yet (fine);
    # anything else non-200 (e.g. a WAF 403) is raised so it surfaces as a
    # failure rather than being mistaken for "no votes".
    first = _session.get(_roll_url(year, 1), headers=_HEADERS, timeout=20)
    if first.status_code == 404:
        _stage([])
        logger.info("house_clerk_votes: no roll calls yet for %d", year)
        return 0
    if first.status_code != 200:
        raise RuntimeError(f"house clerk returned HTTP {first.status_code} (roll 1, {year})")

    top = _max_roll(year)
    lo = max(1, top - settings.votes_limit + 1)
    staged: list[dict] = []
    for n in range(top, lo - 1, -1):  # newest first
        try:
            resp = _session.get(_roll_url(year, n), headers=_HEADERS, timeout=20)
            if resp.status_code != 200:
                continue
            vote = _parse(ET.fromstring(resp.content), year, congress, session)
            if vote:
                staged.append(vote)
        except Exception as exc:
            logger.warning("skipping house roll %d: %s", n, exc)

    if not staged:
        raise ValueError(f"no house votes parsed (year {year}, top roll {top})")

    _stage(staged)
    logger.info("house_clerk_votes: staged %d votes (year %d, rolls %d..%d)", len(staged), year, lo, top)
    return len(staged)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
