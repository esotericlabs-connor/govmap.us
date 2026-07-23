"""Layer 1 pipeline: Senate roll-call votes from the LIS XML.

Sources:
- menu:  https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_{c}_{s}.xml
         (root <vote_summary> -> <votes> -> <vote> -> <vote_number>) — the
         authoritative list of vote numbers for the session.
- vote:  https://www.senate.gov/legislative/LIS/roll_call_votes/vote{c}{s}/vote_{c}_{s}_{NNNNN}.xml
         (root <roll_call_vote>) — per-member positions.

We enumerate from the menu (NOT by probing vote numbers): senate.gov returns a
soft-404 — HTTP 200 with an HTML error page — for non-existent vote files, so a
status-based probe runs away to nonsense. The menu lists exactly the real votes;
we pull the most-recent VOTES_LIMIT of them for positions.

Senate votes key each member by `lis_member_id` (e.g. "S429"), NOT Bioguide, so
positions are staged with the LIS id and the normalizer resolves them to
Bioguide via id_crosswalk.lis.

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
SENATE_MENU = "https://www.senate.gov/legislative/LIS/roll_call_lists"
SOURCE_NAME = "senate_lis_votes"

STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING = STAGING_DIR / "senate_votes_raw.json"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GovMap.us/1.0; +https://govmap.us)"}
_session = requests.Session()


def _menu_url(congress: int, session: int) -> str:
    return f"{SENATE_MENU}/vote_menu_{congress}_{session}.xml"


def _vote_url(congress: int, session: int, n: int) -> str:
    return f"{SENATE_VOTES}/vote{congress}{session}/vote_{congress}_{session}_{n:05d}.xml"


def _int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _menu_numbers(congress: int, session: int) -> list[int]:
    """Vote numbers from the session menu. A menu that won't parse as XML is a
    soft-404 / bad response — raise so it surfaces (vs. looking like 'no votes')."""
    resp = _session.get(_menu_url(congress, session), headers=_HEADERS, timeout=30)
    try:
        menu = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        raise RuntimeError(
            f"senate vote menu not parseable (HTTP {resp.status_code}, {congress}_{session}): {exc}"
        ) from exc
    numbers = [_int(v.findtext("vote_number")) for v in menu.findall("votes/vote")]
    return [n for n in numbers if n is not None]


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    for fmt in ("%B %d, %Y, %I:%M %p", "%B %d, %Y %I:%M %p", "%B %d, %Y"):
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

    numbers = _menu_numbers(congress, session)
    if not numbers:
        _stage([])
        logger.info("senate_lis_votes: no votes in menu yet (congress %d session %d)", congress, session)
        return 0

    numbers = sorted(set(numbers), reverse=True)[: settings.votes_limit]  # newest first
    staged: list[dict] = []
    for n in numbers:
        try:
            resp = _session.get(_vote_url(congress, session, n), headers=_HEADERS, timeout=30)
            vote = _parse(ET.fromstring(resp.content), congress, session, n)
            if vote:
                staged.append(vote)
        except Exception as exc:
            logger.warning("skipping senate vote %d: %s", n, exc)

    if not staged:
        raise ValueError(f"no senate votes parsed ({len(numbers)} in menu)")

    _stage(staged)
    logger.info("senate_lis_votes: staged %d votes", len(staged))
    return len(staged)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
