"""Layer 1 pipeline: accurate per-member sponsored legislation.

The bounded bills pipeline pulls only the most-recently-updated N bills, so a
member's *sponsored* count reflected that slice, not reality (Maria Cantwell
showed "1"). This closes the gap: for every current member (bioguides read from
the legislators staging file — DB-free), it pulls
`GET /member/{bioguide}/sponsored-legislation` for the CURRENT Congress and
stages each as a bill "index" row (identity + title + latest action; sponsor is
that member). The bills normalizer upserts them, so
`/api/members/{id}.sponsored_bills` becomes complete for the current Congress.
Deep detail (actions/cosponsors) still comes from the enriched bills pull.

Reuses the Congress.gov session/retry/header helper from `congress_gov_bills`
(the API key is a header, never a URL param). Bounded per member so a long
career can't blow up one run.

Run directly: `python -m app.pipelines.congress_member_sponsored`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from app.config import settings
from app.pipelines.congress_gov_bills import _PAGE, _get
from app.pipelines.congress_legislators import STAGING_LEGISLATORS
from app.schemas.bill import SponsoredLegislationItemRaw

logger = logging.getLogger(__name__)

SOURCE_NAME = "congress_member_sponsored"

# backend/app/pipelines/congress_member_sponsored.py -> parents[2] == backend/
STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING_PATH = STAGING_DIR / "member_sponsored_raw.json"

# Safety cap on pages per member (250/page). The current Congress rarely holds
# more than a few hundred sponsored bills for even the most prolific member.
_MAX_PAGES = 4


def _bioguides() -> list[str]:
    if not STAGING_LEGISLATORS.exists():
        raise FileNotFoundError(
            f"no legislators staging at {STAGING_LEGISLATORS} — run congress_legislators first"
        )
    records = json.loads(STAGING_LEGISLATORS.read_text())
    ids: list[str] = []
    for r in records:
        bid = (r.get("id") or {}).get("bioguide")
        if bid:
            ids.append(bid)
    return ids


def _sponsored_for(bioguide: str, congress: int) -> list[dict]:
    """Current-Congress sponsored bills for one member as stage-able index rows.
    The endpoint returns newest-first across all congresses, so we stop paging
    once items drop below the current Congress."""
    out: list[dict] = []
    offset = 0
    for _ in range(_MAX_PAGES):
        data = _get(f"member/{bioguide}/sponsored-legislation", limit=_PAGE, offset=offset)
        items = data.get("sponsoredLegislation", []) or []
        if not items:
            break
        older_seen = False
        for it in items:
            try:
                item = SponsoredLegislationItemRaw.model_validate(it)
            except ValidationError as exc:
                logger.warning("skipping sponsored item for %s: %s", bioguide, exc)
                continue
            if item.congress is None or not item.type or item.number is None:
                continue
            if item.congress < congress:
                older_seen = True  # newest-first: the rest are older too
                continue
            if item.congress > congress:
                continue
            out.append(
                {
                    "sponsor_bioguide_id": bioguide,
                    "congress": item.congress,
                    "type": item.type,
                    "number": item.number,
                    "title": item.title,
                    "introduced_date": item.introducedDate.isoformat()
                    if item.introducedDate
                    else None,
                    "latest_action": item.latestAction.text if item.latestAction else None,
                    "latest_action_date": item.latestAction.actionDate.isoformat()
                    if item.latestAction and item.latestAction.actionDate
                    else None,
                    "policy_area": item.policyArea.name if item.policyArea else None,
                }
            )
        if older_seen or not data.get("pagination", {}).get("next"):
            break
        offset += _PAGE
    return out


def run() -> int:
    if not settings.congress_gov_api_key:
        raise RuntimeError(
            "CONGRESS_GOV_API_KEY is not set — required for sponsored legislation"
        )
    congress = settings.congress_number
    bioguides = _bioguides()

    rows: list[dict] = []
    failures = 0
    for bid in bioguides:
        try:
            rows.extend(_sponsored_for(bid, congress))
        except Exception as exc:
            failures += 1
            logger.warning("sponsored pull failed for %s: %s", bid, exc)

    # Total wipe-out (bad key/source) must surface; a few member failures don't.
    if not rows and failures:
        raise RuntimeError(f"sponsored-legislation pull failed for all {failures} members")

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_PATH.write_text(json.dumps(rows))
    logger.info(
        "congress_member_sponsored: staged %d sponsored bills across %d members (%d pull failures)",
        len(rows),
        len(bioguides),
        failures,
    )
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
