"""Layer 1 pipeline: Senate roll-call votes from the LIS XML.

Source: https://www.senate.gov/legislative/LIS/roll_call_votes/vote{c}{s}/vote_{c}_{s}_{NNNNN}.xml
(root <roll_call_vote>). Senate votes key each member by `lis_member_id` (e.g.
"S429"), NOT Bioguide — positions are staged with the LIS id and the normalizer
resolves them to Bioguide via id_crosswalk.lis.

Vote numbers are sequential within a session, so (like House) we binary-search
the current max and pull the most-recent VOTES_LIMIT newest-first. This depends
only on the individual vote-file shape (verified), not the menu index.

Run directly: `python -m app.pipelines.senate_lis_votes`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

from app.config import settings
from app.pipelines.house_clerk_votes import bill_id_from_legis

logger = logging.getLogger(__name__)

SENATE_VOTES = "https://www.senate.gov/legislative/LIS/roll_call_votes"
SOURCE_NAME = "senate_lis_votes"

STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING = STAGING_DIR / "senate_votes_raw.json"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GovMap.us/1.0; +https://govmap.us)"}
_session = requests.Session()


def _vote_url(congress: int, session: int, n: int) -> str:
    return f"{SENATE_VOTES}/vote{congress}{session}/vote_{congress}_{session}_{n:05d}.xml"


def _int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _exists(congress: int, session: int, n: int) -> bool:
    try:
        resp = _session.get(_vote_url(congress, session, n), headers=_HEADERS, timeout=20, stream=True)
        ok = resp.status_code == 200
        resp.close()
        return ok
    except requests.RequestException:
        return False


def _max_vote(congress: int, session: int) -> int:
    if not _exists(congress, session, 1):
        return 0
    lo, hi = 1, 2
    while hi < 4096 and _exists(congress, session, hi):
        lo, hi = hi, hi * 2
    while lo + 1 < hi:  # lo exists, hi does not
        mid = (lo + hi) // 2
        if _exists(congress, session, mid):
            lo = mid
        else:
            hi = mid
    return lo


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    for fmt in ("%B %d, %Y, %I:%M %p", "%B %d, %Y", "%B %d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _senate_bill_id(root: ET.Element, congress: int) -> str | None:
    doc = root.find("document")
    if doc is None:
        return None
    name = doc.findtext("document_name") or doc.findtext("document_short_name") or ""
    return bill_id_from_legis(name, congress)


def _parse(root: ET.Element, congress: int, session: int, n: int) -> dict | None:
    count = root.find("count")
    totals = None
    if count is not None:
        totals = {
            "yea": _int(count.findtext("yeas")),
            "nay": _int(count.findtext("nays")),
            "present": _int(count.findtext("present")),
            "absent": _int(count.findtext("absent")),
        }

    positions = []
    for m in root.findall("members/member"):
        lis = (m.findtext("lis_member_id") or "").strip()
        if not lis:
            continue
        positions.append({"lis_member_id": lis, "position": (m.findtext("vote_cast") or "").strip()})
    if not positions:
        return None

    return {
        "vote_id": f"s{congress}-{session}-{n}",
        "chamber": "senate",
        "congress": congress,
        "session": session,
        "roll_number": n,
        "date": _parse_date(root.findtext("vote_date")),
        "question": (root.findtext("vote_question_text") or root.findtext("question") or "").strip() or None,
        "result": (root.findtext("vote_result") or "").strip() or None,
        "bill_id": _senate_bill_id(root, congress),
        "totals": totals,
        "source_url": _vote_url(congress, session, n),
        "positions": positions,
    }


def _stage(data) -> None:
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(json.dumps(data, indent=2))


def run() -> int:
    congress = settings.congress_number
    session = settings.congress_session

    # Authoritative reachability probe on vote 1: 404 = no votes yet (fine);
    # any other non-200 (e.g. a WAF 403) is raised so it surfaces as a failure.
    first = _session.get(_vote_url(congress, session, 1), headers=_HEADERS, timeout=30)
    if first.status_code == 404:
        _stage([])
        logger.info("senate_lis_votes: no roll calls yet (congress %d session %d)", congress, session)
        return 0
    if first.status_code != 200:
        raise RuntimeError(f"senate returned HTTP {first.status_code} (vote 1)")

    top = _max_vote(congress, session)
    lo = max(1, top - settings.votes_limit + 1)
    staged: list[dict] = []
    for n in range(top, lo - 1, -1):  # newest first
        try:
            resp = _session.get(_vote_url(congress, session, n), headers=_HEADERS, timeout=30)
            if resp.status_code != 200:
                continue
            vote = _parse(ET.fromstring(resp.content), congress, session, n)
            if vote:
                staged.append(vote)
        except Exception as exc:
            logger.warning("skipping senate vote %d: %s", n, exc)

    if not staged:
        raise ValueError(f"no senate votes parsed (top vote {top})")

    _stage(staged)
    logger.info("senate_lis_votes: staged %d votes (votes %d..%d)", len(staged), lo, top)
    return len(staged)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
