"""Layer 1 pipeline: FEC campaign-finance totals per member (Increment 4).

Source: OpenFEC (api.open.fec.gov via the api.data.gov gateway) — free, but keyed
(FEC_API_KEY). For every current member (bioguides + FEC candidate ids + chamber
read from the legislators staging file — DB-free), it selects the candidate id
for the member's *current* office (S… for senators, H… for representatives),
pulls GET /candidate/{id}/totals, and stages the most-recent cycles' totals.

Consistent with the security rule from the bills pipeline: the API key is sent
as the ``X-Api-Key`` header, never a URL query param, so it can't leak into
exceptions/logs/pipeline_status.detail. Skipped (raises, non-fatal) when
FEC_API_KEY is unset, exactly like the bills pipeline without a Congress.gov key.

Run directly: `python -m app.pipelines.fec_finance`.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests
from pydantic import ValidationError

from app.config import settings
from app.pipelines.congress_legislators import STAGING_LEGISLATORS
from app.schemas.finance import CandidateTotalRaw

logger = logging.getLogger(__name__)

FEC_BASE = "https://api.open.fec.gov/v1"
SOURCE_NAME = "fec_finance"

STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING_PATH = STAGING_DIR / "member_finance_raw.json"

_MAX_RETRIES = 4
_TIMEOUT = 45  # OpenFEC's /totals is occasionally slow; 30s wasn't enough.
# Polite pacing between candidates. api.data.gov allows ~1000 req/hr per key;
# spacing calls keeps a full run (~537 members) under the burst throttle so it
# doesn't 429 itself. At ~2/sec a full run is ~4-5 min — which is exactly why
# this pipeline runs off the deploy hot path (scheduler / on-demand only).
_PACE_SECONDS = 0.5
# Chamber (legislators-current term type) -> the FEC candidate-id office prefix.
_CHAMBER_PREFIX = {"sen": "S", "rep": "H"}

_session = requests.Session()


def _fec_get(path: str, **params: Any) -> dict:
    """GET one OpenFEC JSON page with backoff on 429/5xx. Errors carry the path
    only (no params) — and the key is a header — so nothing secret is logged.
    api.data.gov's default limit is ~1000 req/hr per key, so back off politely."""
    params.setdefault("per_page", 100)
    url = f"{FEC_BASE}/{path}/"
    headers = {"X-Api-Key": settings.fec_api_key}
    last_status = 0
    for attempt in range(1, _MAX_RETRIES + 1):
        resp = _session.get(url, params=params, headers=headers, timeout=_TIMEOUT)
        last_status = resp.status_code
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = min(2**attempt, 30)
            logger.warning(
                "openfec %s -> HTTP %d; backoff %ds (attempt %d/%d)",
                path, resp.status_code, wait, attempt, _MAX_RETRIES,
            )
            time.sleep(wait)
            continue
        if not resp.ok:
            raise RuntimeError(f"openfec {path} -> HTTP {resp.status_code}")
        return resp.json()
    raise RuntimeError(
        f"openfec {path} still failing after {_MAX_RETRIES} attempts (HTTP {last_status})"
    )


def _members() -> list[tuple[str, str]]:
    """(bioguide, fec_candidate_id) for members whose current-office FEC id is
    known. Skips members without a matching-chamber FEC candidate id."""
    if not STAGING_LEGISLATORS.exists():
        raise FileNotFoundError(
            f"no legislators staging at {STAGING_LEGISLATORS} — run congress_legislators first"
        )
    records = json.loads(STAGING_LEGISLATORS.read_text())
    out: list[tuple[str, str]] = []
    for r in records:
        ident = r.get("id") or {}
        bioguide = ident.get("bioguide")
        fec_ids = ident.get("fec") or []
        terms = r.get("terms") or []
        if not bioguide or not fec_ids or not terms:
            continue
        prefix = _CHAMBER_PREFIX.get(terms[-1].get("type"))
        if not prefix:
            continue
        candidate_id = next((f for f in fec_ids if f.startswith(prefix)), None)
        if candidate_id:
            out.append((bioguide, candidate_id))
    return out


def _totals_for(bioguide: str, candidate_id: str, keep: int) -> list[dict]:
    data = _fec_get(f"candidate/{candidate_id}/totals", sort="-cycle", per_page=keep)
    rows: list[dict] = []
    for it in (data.get("results") or [])[:keep]:
        try:
            t = CandidateTotalRaw.model_validate(it)
        except ValidationError as exc:
            logger.warning("skipping totals row for %s: %s", candidate_id, exc)
            continue
        if t.cycle is None:
            continue
        rows.append(
            {
                "bioguide_id": bioguide,
                "cycle": t.cycle,
                "fec_candidate_id": candidate_id,
                "receipts": t.receipts,
                "disbursements": t.disbursements,
                "cash_on_hand": t.cash_on_hand_end_period,
                "debts": t.debts_owed_by_committee,
                "individual_contributions": t.individual_contributions,
                "pac_contributions": t.other_political_committee_contributions,
                "party_contributions": t.political_party_committee_contributions,
                "coverage_start": t.coverage_start_date.isoformat() if t.coverage_start_date else None,
                "coverage_end": t.coverage_end_date.isoformat() if t.coverage_end_date else None,
            }
        )
    return rows


def run() -> int:
    if not settings.fec_api_key:
        raise RuntimeError(
            "FEC_API_KEY is not set — required for the campaign-finance pipeline "
            "(free key at https://api.data.gov/signup/)"
        )
    keep = settings.fec_cycles_kept
    members = _members()

    rows: list[dict] = []
    failures = 0
    for bioguide, candidate_id in members:
        try:
            rows.extend(_totals_for(bioguide, candidate_id, keep))
        except Exception as exc:
            failures += 1
            logger.warning("finance pull failed for %s (%s): %s", bioguide, candidate_id, exc)
        time.sleep(_PACE_SECONDS)  # stay under the api.data.gov burst throttle

    # Total wipe-out (bad key / source down) must surface; a few misses don't.
    if not rows and failures:
        raise RuntimeError(f"FEC totals pull failed for all {failures} candidates")

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_PATH.write_text(json.dumps(rows))
    logger.info(
        "fec_finance: staged %d finance rows across %d candidates (%d pull failures)",
        len(rows), len(members), failures,
    )
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
