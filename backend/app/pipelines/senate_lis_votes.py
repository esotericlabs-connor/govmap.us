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

The production menu request returned HTTP 403. This stays the PRIMARY source;
refresh_votes falls back to voteview_senate_votes when it raises. A 403 alone
does not identify the upstream blocking policy.

Run directly: `python -m app.pipelines.senate_lis_votes`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

from app.config import settings
from app.pipelines.house_clerk_votes import bill_id_from_legis
from app.pipelines.staging import write_json_atomic
from app.services.bounded_http import read_body
from app.services.safe_parse import parse_xml

logger = logging.getLogger(__name__)

SENATE_VOTES = "https://www.senate.gov/legislative/LIS/roll_call_votes"
SENATE_MENU = "https://www.senate.gov/legislative/LIS/roll_call_lists"
SOURCE_NAME = "senate_lis_votes"

STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING = STAGING_DIR / "senate_votes_raw.json"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GovMap.us/1.0; +https://govmap.us)"}
_session = requests.Session()

# The full-session menu is about 170 KiB and a vote file about 30 KiB.
_MAX_XML_BYTES = 8 * 1024 * 1024
_BODY_DEADLINE_SECONDS = 60


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
    """Vote numbers from the session menu. A non-200, a body that won't parse as
    XML, or a parseable document that isn't a <vote_summary> menu is a block /
    soft-404 / bad response — raise so it surfaces (vs. looking like 'no votes',
    which would also suppress the Voteview fallback in refresh_votes)."""
    label = f"senate vote menu {congress}_{session}"
    resp = _session.get(_menu_url(congress, session), headers=_HEADERS, timeout=30, stream=True)
    try:
        if resp.status_code != 200:
            raise RuntimeError(f"senate vote menu returned HTTP {resp.status_code} ({congress}_{session})")
        body = read_body(
            resp, max_bytes=_MAX_XML_BYTES, deadline_s=_BODY_DEADLINE_SECONDS, label=label
        )
    finally:
        resp.close()
    try:
        menu = parse_xml(body, label=label)
    except ET.ParseError as exc:
        raise RuntimeError(f"senate vote menu not parseable ({congress}_{session}): {exc}") from exc
    if menu.tag != "vote_summary":
        raise RuntimeError(f"senate vote menu has unexpected root <{menu.tag}> ({congress}_{session})")
    if menu.find("votes") is None:
        raise ValueError("senate vote menu is missing its votes element")
    numbers: list[int] = []
    for vote in menu.findall("votes/vote"):
        number = _int(vote.findtext("vote_number"))
        if number is None or number < 1:
            raise ValueError("senate vote menu contains an invalid vote number")
        numbers.append(number)
    return numbers


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
    write_json_atomic(STAGING, data, indent=2)


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
        resp = _session.get(_vote_url(congress, session, n), headers=_HEADERS, timeout=30, stream=True)
        try:
            if resp.status_code != 200:
                raise RuntimeError(f"senate vote {n} returned HTTP {resp.status_code}")
            label = f"senate vote {n}"
            body = read_body(
                resp, max_bytes=_MAX_XML_BYTES, deadline_s=_BODY_DEADLINE_SECONDS, label=label
            )
            root = parse_xml(body, label=label)
            if root.tag != "roll_call_vote" or _int(root.findtext("vote_number")) != n:
                raise ValueError(f"senate vote {n} is not a matching roll-call document")
            vote = _parse(root, congress, session, n)
            if not vote:
                raise ValueError(f"senate vote {n} has no member positions")
            staged.append(vote)
        finally:
            resp.close()

    if not staged:
        raise ValueError(f"no senate votes parsed ({len(numbers)} in menu)")

    _stage(staged)
    logger.info("senate_lis_votes: staged %d votes", len(staged))
    return len(staged)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
