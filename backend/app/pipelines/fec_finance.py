"""Layer 1 pipeline: FEC campaign-finance totals per member (Increment 4).

Source: OpenFEC (api.open.fec.gov via the api.data.gov gateway) — free, keyed
(FEC_API_KEY). To respect api.data.gov's ~1000 req/hr limit, this pulls the
**bulk** aggregate endpoint `GET /candidates/totals` once per chamber for the
configured cycle (a handful of paginated calls) instead of one call per member
(~537, which exhausted the hourly budget and 429'd). It builds a
`candidate_id -> totals` index, then maps each current member (bioguide +
current-office FEC id, chosen by S/H prefix, read from the legislators staging
file — DB-free) onto its row.

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
# Brief pause between the (few) bulk pages, to stay polite under the throttle.
_PACE_SECONDS = 0.5
# Safety cap on pages per chamber (100 candidates/page). A chamber-cycle is well
# under this; the cap just bounds a pathological response.
# We query the bulk endpoint filtered to OUR members' candidate ids (batched),
# not the whole field of thousands of challengers — a few targeted calls that
# also stay well under api.data.gov's ~1000 req/hr limit.
_ID_BATCH = 50           # candidate_ids per request (repeatable filter; short URL)
_BATCH_MAX_PAGES = 3     # 50 ids × _CYCLE_SPAN cycles fits in ~2 pages; cap for safety
# How many 2-year cycles back to include (newest wins). Covers all three Senate
# classes + the House regardless of which year each member last ran.
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
        if resp.status_code == 429 or resp.status_code >= 500:
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
        "individual_contributions": t.individual_contributions,
        "pac_contributions": t.other_political_committee_contributions,
        "party_contributions": t.political_party_committee_contributions,
        "coverage_start": t.coverage_start_date.isoformat() if t.coverage_start_date else None,
        "coverage_end": t.coverage_end_date.isoformat() if t.coverage_end_date else None,
    }


def _totals_index(candidate_ids: list[str], cycles: list[int]) -> dict[str, dict]:
    """candidate_id -> most-recent totals row, fetched by filtering the bulk
    endpoint on OUR members' candidate ids (batched) across `cycles`. Targeted
    (no scanning thousands of challengers) and cheap: ~2 pages per 50-id batch.
    The newest cycle per candidate is chosen client-side (no `sort` param —
    OpenFEC 422s on sort fields it doesn't allow for this endpoint)."""
    index: dict[str, dict] = {}
    for start in range(0, len(candidate_ids), _ID_BATCH):
        batch = candidate_ids[start : start + _ID_BATCH]
        for page in range(1, _BATCH_MAX_PAGES + 1):
            data = _fec_get(
                "candidates/totals",
                candidate_id=batch,   # repeatable filter — requests encodes the list
                cycle=cycles,         # repeatable filter (OR across cycles)
                election_full="false",
                per_page=100,
                page=page,
            )
            results = data.get("results") or []
            for it in results:
                cid = it.get("candidate_id")
                if not cid:
                    continue
                prev = index.get(cid)
                if prev is None or (it.get("cycle") or 0) > (prev.get("cycle") or 0):
                    index[cid] = it  # keep the newest cycle per candidate
            pages = (data.get("pagination") or {}).get("pages") or 1
            if page >= pages or not results:
                break
            time.sleep(_PACE_SECONDS)
    return index


def run() -> int:
    if not settings.fec_api_key:
        raise RuntimeError(
            "FEC_API_KEY is not set — required for the campaign-finance pipeline "
            "(free key at https://api.data.gov/signup/)"
        )
    base = settings.fec_cycle
    cycles = [base - 2 * i for i in range(_CYCLE_SPAN)]  # e.g. 2026, 2024, 2022, 2020
    by_candidate = {cid: bio for bio, cid in _members()}  # candidate_id -> bioguide
    index = _totals_index(list(by_candidate), cycles)
    if not index:
        raise RuntimeError(
            f"OpenFEC returned no totals for {len(by_candidate)} candidates, cycles {cycles}"
        )

    rows: list[dict] = []
    for candidate_id, raw in index.items():
        bioguide = by_candidate.get(candidate_id)
        if not bioguide:
            continue
        try:
            t = CandidateTotalRaw.model_validate(raw)
        except ValidationError as exc:
            logger.warning("skipping totals for %s (%s): %s", bioguide, candidate_id, exc)
            continue
        if t.cycle is None:
            continue
        rows.append(_row(bioguide, candidate_id, t))

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_PATH.write_text(json.dumps(rows))
    logger.info(
        "fec_finance: staged %d finance rows (cycles %s; %d of %d members matched)",
        len(rows), cycles, len(rows), len(by_candidate),
    )
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
