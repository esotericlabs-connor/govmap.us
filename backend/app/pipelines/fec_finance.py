"""Layer 1 pipeline: FEC campaign-finance totals per member (Increment 4).

Source: OpenFEC (api.open.fec.gov via the api.data.gov gateway) — free, keyed
(FEC_API_KEY). Pulls the **per-candidate** endpoint
``GET /candidate/{candidate_id}/totals/`` — one call per current member. This is
deliberately NOT the batched ``/candidates/totals/`` aggregate: that aggregate
only reports itemized-individual + PAC money and omits unitemized (small-dollar)
individuals, party money, and the combined individual total, which made every
member read as "PACs 100%". The per-candidate endpoint carries the full Form 3
line-item breakdown, so we accept ~one call per member (paced well under
api.data.gov's ~1000 req/hr limit) in exchange for correct, rich data.

For each member (bioguide + current-office FEC id, chosen by S/H prefix, read
from the legislators staging file — DB-free) it fetches that candidate's totals
for the recent cycles and keeps the newest cycle that actually has receipts.

The API key is sent as the ``X-Api-Key`` header, never a URL query param, so it
can't leak into exceptions/logs/pipeline_status.detail. Skipped (raises,
non-fatal) when FEC_API_KEY is unset, like the bills pipeline without a key.

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
_TIMEOUT = 45  # OpenFEC's totals endpoint is occasionally slow; 30s wasn't enough.
# Brief pause between per-candidate calls to stay polite under the throttle.
# ~535 members × this delay is a few minutes and stays well under ~1000 req/hr.
_PACE_SECONDS = 0.3
# 429 handling: api.data.gov's hourly budget doesn't reset for up to an hour, so
# a 429 storm means the budget is spent — don't grind through all ~535 members.
_RATE_LIMIT_RETRIES = 2   # short retries for a per-second burst blip, then bail
_RATE_LIMIT_ABORT = 8     # consecutive rate-limited members -> abort the whole run


class _RateLimited(Exception):
    """OpenFEC returned 429 after the short burst retries — the hourly budget is
    (near) exhausted, so the caller should stop rather than keep hammering."""
# How many 2-year cycles back to consider (newest with activity wins). Covers all
# three Senate classes + the House regardless of which year each member last ran.
_CYCLE_SPAN = 4
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
        if resp.status_code == 429:
            # A couple of short retries cover a per-second burst; beyond that the
            # hourly budget is spent (backing off 30s won't help within the hour),
            # so raise and let run() abort fast instead of grinding every member.
            if attempt <= _RATE_LIMIT_RETRIES:
                time.sleep(attempt)
                continue
            raise _RateLimited(path)
        if resp.status_code >= 500:
            wait = min(2**attempt, 30)
            logger.warning(
                "openfec %s -> HTTP %d; backoff %ds (attempt %d/%d)",
                path, resp.status_code, wait, attempt, _MAX_RETRIES,
            )
            time.sleep(wait)
            continue
        if not resp.ok:
            # Include the response body — OpenFEC's 4xx (esp. 422) says exactly
            # which parameter it rejected. No secret leaks: the key is a header,
            # and the body only echoes validation detail, not the key.
            body = " ".join(resp.text.split())[:300]
            raise RuntimeError(f"openfec {path} -> HTTP {resp.status_code}: {body}")
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


def _row(bioguide: str, candidate_id: str, t: CandidateTotalRaw) -> dict:
    return {
        "bioguide_id": bioguide,
        "cycle": t.cycle,
        "fec_candidate_id": candidate_id,
        "receipts": t.receipts,
        "disbursements": t.disbursements,
        "cash_on_hand": t.cash_on_hand_end_period,
        "debts": t.debts_owed_by_committee,
        "contributions": t.contributions,
        "individual_contributions": t.individual_contributions,
        "individual_itemized": t.individual_itemized_contributions,
        "individual_unitemized": t.individual_unitemized_contributions,
        "pac_contributions": t.other_political_committee_contributions,
        "party_contributions": t.political_party_committee_contributions,
        "transfers": t.transfers_from_other_authorized_committee,
        "candidate_contribution": t.candidate_contribution,
        "other_receipts": t.other_receipts,
        "loans": t.loans,
        "operating_expenditures": t.operating_expenditures,
        "refunded_individual": t.refunded_individual_contributions,
        "coverage_start": t.coverage_start_date.isoformat() if t.coverage_start_date else None,
        "coverage_end": t.coverage_end_date.isoformat() if t.coverage_end_date else None,
    }


def _best_cycle(results: list[dict]) -> dict | None:
    """Pick the newest cycle that actually has receipts (so a member who just
    filed an empty statement for the current cycle still shows their last real
    campaign); fall back to the newest cycle present."""
    if not results:
        return None
    with_money = [r for r in results if (r.get("receipts") or 0) > 0]
    pool = with_money or results
    return max(pool, key=lambda r: r.get("cycle") or 0)


def _candidate_total(candidate_id: str, cycles: list[int]) -> dict | None:
    """The newest cycle-with-activity totals row for one candidate, or None."""
    data = _fec_get(
        f"candidate/{candidate_id}/totals",
        cycle=cycles,          # repeatable filter (OR across cycles) — bounds to ≤4 rows
        election_full="false",  # per 2-year cycle, not the full Senate election span
        per_page=100,
    )
    return _best_cycle(data.get("results") or [])


def run() -> int:
    if not settings.fec_api_key:
        raise RuntimeError(
            "FEC_API_KEY is not set — required for the campaign-finance pipeline "
            "(free key at https://api.data.gov/signup/)"
        )
    base = settings.fec_cycle
    cycles = [base - 2 * i for i in range(_CYCLE_SPAN)]  # e.g. 2026, 2024, 2022, 2020
    members = _members()

    rows: list[dict] = []
    unmatched: list[str] = []
    consecutive_rl = 0
    for bioguide, candidate_id in members:
        try:
            raw = _candidate_total(candidate_id, cycles)
        except _RateLimited:
            # Budget spent — abort once we've seen a run of consecutive 429s
            # rather than burning minutes on the remaining members. Whatever was
            # staged so far still loads; a re-run in a fresh hour continues.
            consecutive_rl += 1
            if consecutive_rl >= _RATE_LIMIT_ABORT:
                logger.warning(
                    "fec_finance: OpenFEC rate limit hit — aborting after %d consecutive 429s "
                    "(staged %d of %d members). Re-run in a fresh hour (api.data.gov resets "
                    "hourly) or request a higher rate limit for the key.",
                    consecutive_rl, len(rows), len(members),
                )
                break
            continue
        except Exception as exc:
            # One member's committee 404/blip shouldn't sink the batch.
            logger.warning("skipping finance for %s (%s): %s", bioguide, candidate_id, exc)
            unmatched.append(f"{bioguide}/{candidate_id}")
            time.sleep(_PACE_SECONDS)
            continue
        consecutive_rl = 0
        if not raw:
            unmatched.append(f"{bioguide}/{candidate_id}")
            time.sleep(_PACE_SECONDS)
            continue
        try:
            t = CandidateTotalRaw.model_validate(raw)
        except ValidationError as exc:
            logger.warning("skipping totals for %s (%s): %s", bioguide, candidate_id, exc)
            time.sleep(_PACE_SECONDS)
            continue
        if t.cycle is not None:
            rows.append(_row(bioguide, candidate_id, t))
        time.sleep(_PACE_SECONDS)

    if not rows:
        raise RuntimeError(
            f"OpenFEC returned no totals — the api.data.gov key is rate-limited (429) from the "
            f"first call, so its hourly budget is spent. Re-run in a fresh hour, or request a "
            f"higher rate limit for the key (~{len(members)} calls are needed per full run)."
        )

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_PATH.write_text(json.dumps(rows))
    logger.info(
        "fec_finance: staged %d finance rows (cycles %s; %d of %d members matched)",
        len(rows), cycles, len(rows), len(members),
    )

    # Name any members with no FEC totals so a real gap (a wrong candidate id) is
    # distinguishable from a legitimate one (never ran a federal campaign / a
    # dormant committee).
    if unmatched:
        logger.info(
            "fec_finance: %d member(s) had no FEC totals in %s: %s",
            len(unmatched), cycles, ", ".join(unmatched),
        )
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
