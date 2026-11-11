"""Layer 1 pipeline: Senate roll-call votes from Voteview (FALLBACK source).

The official Senate LIS menu returned HTTP 403 in production. Voteview (UCLA,
https://voteview.com) publishes roll-call CSVs with Bioguide IDs, excluding
quorum calls and vacated votes. refresh_votes calls this only when the official
pull raises. Fallback runs remain partial: downloading a file does not establish
its completeness or freshness relative to the official feed.

Citation: Lewis, Jeffrey B., Keith Poole, Howard Rosenthal, Adam Boche, Aaron
Rudkin, and Luke Sonnet. Voteview: Congressional Roll-Call Votes Database.
https://voteview.com/

Sources (one file per Congress, under https://voteview.com/static/data/out/):
- rollcalls/S{c}_rollcalls.csv — one row per roll call; `session` +
  `clerk_rollnumber` are the official Senate session + vote number.
- members/S{c}_members.csv     — ICPSR id -> bioguide_id.
- votes/S{c}_votes.csv         — one row per (roll call, member) cast_code.

Staged to the SAME file and shape as senate_lis_votes — same vote_id
`s{c}-{session}-{vote number}`, so a later official pull overwrites these rows in
place — except positions carry `bioguide_id` directly (no LIS crosswalk) and
each vote carries `provenance: "voteview"`. `source_url` points to the Voteview
votes dataset so attribution survives normalization without a schema migration.

Positions use the official Senate vocabulary. Voteview cast codes: 1 Yea;
2/3 paired/announced yea; 4/5 announced/paired nay; 6 Nay; 7/8 Present; 9 not
voting; 0 not a member. Pairs and announcements are not recorded votes — the
official tally counts those senators as not voting — so 2-5 and 9 stage as
"Not Voting", and totals (the LIS keys yea/nay/present/absent) are recomputed
from the staged positions.

Run directly: `python -m app.pipelines.voteview_senate_votes`.
"""

from __future__ import annotations

import csv
import html
import io
import json
import logging
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import TypeVar

import requests
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.pipelines.staging import write_json_atomic
from app.schemas.vote import (
    VoteviewCastRaw,
    VoteviewMemberRaw,
    VoteviewRollcallRaw,
    VoteviewStagedVote,
)

logger = logging.getLogger(__name__)

VOTEVIEW_BASE = "https://voteview.com/static/data/out"
SOURCE_NAME = "voteview_senate_votes"
PROVENANCE = "voteview"

STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING = STAGING_DIR / "senate_votes_raw.json"  # shared with senate_lis_votes

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GovMap.us/1.0; +https://govmap.us)"}
_session = requests.Session()
_TIMEOUT = (10, 60)
# S{c}_votes.csv is ~3 MB by the end of a Congress; anything far larger is not
# the file we expect, so stop reading instead of buffering it.
_MAX_CSV_BYTES = 32 * 1024 * 1024

_ROLLCALL_COLUMNS = frozenset(
    {"congress", "chamber", "rollnumber", "date", "session", "clerk_rollnumber",
     "yea_count", "nay_count", "bill_number", "vote_result", "vote_question"}
)
_MEMBER_COLUMNS = frozenset({"congress", "chamber", "icpsr", "bioguide_id"})
_CAST_COLUMNS = frozenset({"congress", "chamber", "rollnumber", "icpsr", "cast_code"})

_POSITION = {
    1: "Yea",
    2: "Not Voting", 3: "Not Voting", 4: "Not Voting", 5: "Not Voting",
    6: "Nay",
    7: "Present", 8: "Present",
    9: "Not Voting",
}
_TOTAL_KEY = {"Yea": "yea", "Nay": "nay", "Present": "present", "Not Voting": "absent"}
_YEA_CODES = frozenset({1, 2, 3})
_NAY_CODES = frozenset({4, 5, 6})

_BIOGUIDE = re.compile(r"^[A-Z]\d{6}$")
# Longest prefixes first; nominations (PN...), treaties and procedural votes
# don't match and get no bill_id.
_BILL = re.compile(r"^(HCONRES|SCONRES|HJRES|SJRES|HRES|SRES|HR|S)(\d+)$")

M = TypeVar("M", bound=BaseModel)


def _csv_url(kind: str, congress: int) -> str:
    return f"{VOTEVIEW_BASE}/{kind}/S{congress}_{kind}.csv"


def bill_id_from_voteview(bill_number: str | None, congress: int) -> str | None:
    """"S5" -> "s5-119"; "HCONRES86" -> "hconres86-119"; "PN1113" -> None."""
    m = _BILL.match((bill_number or "").strip().upper())
    return f"{m.group(1).lower()}{int(m.group(2))}-{congress}" if m else None


def _text(raw: str | None, limit: int | None = None) -> str | None:
    # Voteview text cells carry HTML entities (e.g. "Medicare &#38; Medicaid").
    if not raw:
        return None
    text = html.unescape(raw).strip()
    if limit is not None:
        text = text[:limit]
    return text or None


def _fetch_csv(kind: str, congress: int, required: frozenset[str]) -> list[dict[str, str]]:
    """Download one Voteview CSV and return its rows. Raises on a non-200, an
    oversized body, or a header missing a column we depend on — an upstream
    format change must fail the pull, not stage garbage."""
    resp = _session.get(_csv_url(kind, congress), headers=_HEADERS, timeout=_TIMEOUT, stream=True)
    try:
        if resp.status_code != 200:
            raise RuntimeError(f"voteview {kind} returned HTTP {resp.status_code}")
        body = bytearray()
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            body.extend(chunk)
            if len(body) > _MAX_CSV_BYTES:
                raise RuntimeError(f"voteview {kind} is larger than {_MAX_CSV_BYTES} bytes")
    finally:
        resp.close()
    text = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""), restkey="_extra", strict=True)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(f"voteview {kind} csv is missing column(s) {sorted(missing)}")
    if len(reader.fieldnames or ()) != len(set(reader.fieldnames or ())):
        raise ValueError(f"voteview {kind} csv has duplicate columns")
    rows = list(reader)
    if any("_extra" in row or None in row.values() for row in rows):
        raise ValueError(f"voteview {kind} csv has an incomplete or oversized row")
    return rows


def _validated(model: type[M], rows: list[dict[str, str]], kind: str) -> list[M]:
    """Do not publish partial positions when one of the source files is bad."""
    if not rows:
        raise ValueError(f"voteview {kind}: empty source file")
    good: list[M] = []
    for number, row in enumerate(rows, start=2):
        try:
            good.append(model.model_validate(row))
        except ValidationError:
            raise ValueError(f"voteview {kind}: invalid row {number}; not staging") from None
    return good


def _current_rollcalls(congress: int, session: int) -> list[VoteviewRollcallRaw]:
    """The newest VOTES_LIMIT Senate roll calls of the tracked session, newest
    first, keyed by the official vote number."""
    rows = _validated(
        VoteviewRollcallRaw, _fetch_csv("rollcalls", congress, _ROLLCALL_COLUMNS), "rollcalls"
    )
    by_number: dict[int, VoteviewRollcallRaw] = {}
    seen_rolls: set[int] = set()
    for rc in rows:
        if rc.congress != congress or rc.chamber != "Senate":
            raise ValueError("voteview rollcalls contains a different Congress or chamber")
        if rc.rollnumber in seen_rolls:
            raise ValueError("voteview rollcalls contains duplicate internal roll numbers")
        seen_rolls.add(rc.rollnumber)
        if rc.session == session:
            if rc.clerk_rollnumber in by_number:
                raise ValueError("voteview rollcalls contains duplicate official vote numbers")
            by_number[rc.clerk_rollnumber] = rc
    newest = sorted(by_number, reverse=True)[: settings.votes_limit]
    return [by_number[n] for n in newest]


def _bioguide_by_icpsr(congress: int) -> dict[int, str]:
    rows = _validated(
        VoteviewMemberRaw, _fetch_csv("members", congress, _MEMBER_COLUMNS), "members"
    )
    mapping: dict[int, str] = {}
    for m in rows:
        if m.congress != congress:
            raise ValueError("voteview members contains a different Congress")
        bio = (m.bioguide_id or "").strip()
        if m.chamber == "Senate" and _BIOGUIDE.match(bio):
            if m.icpsr in mapping and mapping[m.icpsr] != bio:
                raise ValueError("voteview members contains conflicting Bioguide mappings")
            mapping[m.icpsr] = bio
    return mapping


def _casts_by_roll(congress: int, wanted: set[int]) -> dict[int, list[VoteviewCastRaw]]:
    rows = _validated(VoteviewCastRaw, _fetch_csv("votes", congress, _CAST_COLUMNS), "votes")
    grouped: dict[int, list[VoteviewCastRaw]] = defaultdict(list)
    for cast in rows:
        if cast.congress != congress:
            raise ValueError("voteview votes contains a different Congress")
        if cast.chamber == "Senate" and cast.rollnumber in wanted:
            grouped[cast.rollnumber].append(cast)
    return grouped


def _tally_mismatch(rc: VoteviewRollcallRaw, codes: list[int]) -> bool:
    """Voteview's own yea/nay counts must fall between the strict (1 / 6) and
    pair-inclusive (1-3 / 4-6) cast counts; otherwise the votes file disagrees
    with the rollcalls file (e.g. one was caught mid-update)."""
    if rc.yea_count is None or rc.nay_count is None:
        return True
    yea_strict = codes.count(1)
    nay_strict = codes.count(6)
    yea_loose = sum(1 for c in codes if c in _YEA_CODES)
    nay_loose = sum(1 for c in codes if c in _NAY_CODES)
    return not (
        yea_strict <= rc.yea_count <= yea_loose and nay_strict <= rc.nay_count <= nay_loose
    )


def _reusable_staged_count(congress: int, session: int) -> int | None:
    """Vote count of a still-fresh Voteview staging file for this Congress and
    session, or None when it must be re-downloaded."""
    max_age = settings.voteview_min_refetch_hours * 3600
    if max_age <= 0:
        return None
    try:
        age = time.time() - STAGING.stat().st_mtime
        staged = json.loads(STAGING.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        logger.warning("voteview staging cannot be reused; downloading again")
        return None
    if age < 0 or age >= max_age or not isinstance(staged, list) or not staged:
        return None
    if len(staged) != settings.votes_limit:
        return None
    seen: set[str] = set()
    for raw in staged:
        try:
            vote = VoteviewStagedVote.model_validate(raw)
        except ValidationError:
            logger.warning("voteview staging failed validation; downloading again")
            return None
        expected_id = f"s{congress}-{session}-{vote.roll_number}"
        if (vote.congress != congress or vote.session != session
                or vote.vote_id != expected_id or vote.vote_id in seen
                or vote.source_url != _csv_url("votes", congress)):
            return None
        seen.add(vote.vote_id)
        totals = dict.fromkeys(_TOTAL_KEY.values(), 0)
        members: set[str] = set()
        for position in vote.positions:
            if position.bioguide_id in members:
                return None
            members.add(position.bioguide_id)
            totals[_TOTAL_KEY[position.position]] += 1
        if totals != vote.totals:
            return None
    return len(staged)


def _stage(data: list[dict]) -> None:
    write_json_atomic(STAGING, data, indent=2)


def run() -> int:
    congress = settings.congress_number
    session = settings.congress_session

    reused = _reusable_staged_count(congress, session)
    if reused is not None:
        logger.info(
            "voteview_senate_votes: reusing %d staged votes (< %dh old)",
            reused, settings.voteview_min_refetch_hours,
        )
        return reused

    rollcalls = _current_rollcalls(congress, session)
    if not rollcalls:
        _stage([])
        logger.info("voteview_senate_votes: no roll calls yet (congress %d session %d)", congress, session)
        return 0

    bioguide_by_icpsr = _bioguide_by_icpsr(congress)
    casts = _casts_by_roll(congress, {rc.rollnumber for rc in rollcalls})

    staged: list[dict] = []
    for rc in rollcalls:  # newest first
        positions: list[dict] = []
        totals = {"yea": 0, "nay": 0, "present": 0, "absent": 0}
        codes: list[int] = []
        seen: set[str] = set()
        for cast in casts.get(rc.rollnumber, []):
            if cast.cast_code == 0:  # not a member at the time of this vote
                continue
            position = _POSITION.get(cast.cast_code)
            if position is None:
                raise ValueError(f"voteview roll {rc.clerk_rollnumber}: unknown cast code")
            codes.append(cast.cast_code)
            bio = bioguide_by_icpsr.get(cast.icpsr)
            if not bio:
                raise ValueError(
                    f"voteview roll {rc.clerk_rollnumber}: ICPSR {cast.icpsr} has no Bioguide mapping"
                )
            if bio in seen:
                raise ValueError(f"voteview roll {rc.clerk_rollnumber}: duplicate member position")
            seen.add(bio)
            positions.append({"bioguide_id": bio, "position": position})
            totals[_TOTAL_KEY[position]] += 1
        if not positions:
            raise ValueError(f"voteview roll {rc.clerk_rollnumber}: no member positions; not staging")
        if _tally_mismatch(rc, codes):
            raise ValueError(f"voteview roll {rc.clerk_rollnumber}: tally mismatch; not staging")
        staged.append({
            "vote_id": f"s{congress}-{session}-{rc.clerk_rollnumber}",
            "chamber": "senate",
            "congress": congress,
            "session": session,
            "roll_number": rc.clerk_rollnumber,
            "date": rc.vote_date.isoformat(),
            "question": _text(rc.vote_question),
            "result": _text(rc.vote_result, limit=120),
            "bill_id": bill_id_from_voteview(rc.bill_number, congress),
            "totals": totals,
            "source_url": _csv_url("votes", congress),
            "provenance": PROVENANCE,
            "positions": positions,
        })

    _stage(staged)
    logger.info(
        "voteview_senate_votes: staged %d votes (congress %d session %d, votes %d..%d)",
        len(staged), congress, session, staged[-1]["roll_number"], staged[0]["roll_number"],
    )
    return len(staged)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
