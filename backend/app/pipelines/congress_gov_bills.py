"""Layer 1 pipeline: pull current-Congress bills from the Congress.gov v3 API.

Bounded + incremental. Each run pulls the most-recently-updated bills
(sort=updateDate desc) up to CONGRESS_GOV_BILL_LIMIT, and for each fetches
detail + actions + cosponsors, validates, and stages. Because the list is
sorted by update date, changed/new bills always surface first, so scheduled
runs keep the corpus fresh; raising the cap (or a future updateDate-window
backfill) widens coverage toward the full ~15k-bill corpus.

This is the golden pattern extended for a *keyed REST* source (vs. the bulk-file
congress_legislators): pull -> validate (skip bad rows, fail loudly if nothing
survives) -> stage, DB-free. The Congress.gov key is sent as the `X-Api-Key`
HEADER, never a URL query param, so it can't leak into exceptions, logs, or the
pipeline_status.detail column.

Requires CONGRESS_GOV_API_KEY. Run directly:
`python -m app.pipelines.congress_gov_bills`.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.schemas.bill import (
    BillActionRaw,
    BillDetailRaw,
    BillListItemRaw,
    BillSummaryRaw,
    BillTextVersionRaw,
    CosponsorRaw,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.congress.gov/v3"
SOURCE_NAME = "congress_gov_bills"

# backend/app/pipelines/congress_gov_bills.py -> parents[2] == backend/
STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING_BILLS = STAGING_DIR / "bills_raw.json"

_PAGE = 250  # Congress.gov max page size
_MAX_RETRIES = 4
_SUBRESOURCE_MAX_PAGES = 20  # generous safety cap (bills rarely exceed a page)

_session = requests.Session()


def _get(path: str, **params: Any) -> dict:
    """GET one Congress.gov JSON page with backoff on 429/5xx. Errors are raised
    with the path only — never the URL/params — so the API key (sent as a
    header) and query never reach a log or status row."""
    params.setdefault("format", "json")
    url = f"{API_BASE}/{path}"
    headers = {"X-Api-Key": settings.congress_gov_api_key}
    last_status = 0
    for attempt in range(1, _MAX_RETRIES + 1):
        resp = _session.get(url, params=params, headers=headers, timeout=30)
        last_status = resp.status_code
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = min(2**attempt, 30)
            logger.warning(
                "congress.gov %s -> HTTP %d; backoff %ds (attempt %d/%d)",
                path, resp.status_code, wait, attempt, _MAX_RETRIES,
            )
            time.sleep(wait)
            continue
        if not resp.ok:
            raise RuntimeError(f"congress.gov {path} -> HTTP {resp.status_code}")
        return resp.json()
    raise RuntimeError(
        f"congress.gov {path} still failing after {_MAX_RETRIES} attempts (HTTP {last_status})"
    )


def _paginate(path: str, key: str, cap: int = 10**9) -> list[dict]:
    """Follow pagination.next, collecting items under `key`, up to `cap`."""
    out: list[dict] = []
    offset = 0
    for _ in range(_SUBRESOURCE_MAX_PAGES):
        data = _get(path, limit=_PAGE, offset=offset)
        items = data.get(key, []) or []
        out.extend(items)
        if len(out) >= cap or len(items) < _PAGE or not data.get("pagination", {}).get("next"):
            break
        offset += _PAGE
    return out[:cap]


def _validate_each(records: list, model: type[BaseModel], label: str) -> list[dict]:
    """Validate each record; skip and log bad ones individually (a sub-resource
    quirk shouldn't drop a whole bill)."""
    valid: list[dict] = []
    for record in records:
        try:
            valid.append(model.model_validate(record).model_dump(mode="json"))
        except ValidationError as exc:
            logger.warning("skipping invalid %s: %s", label, exc)
    return valid


def _bill_list(congress: int, cap: int) -> list[BillListItemRaw]:
    """The most-recently-updated bills for the congress, newest first, up to cap.
    Passing 'updateDate desc' yields the URL-encoded 'sort=updateDate+desc'."""
    collected: list[BillListItemRaw] = []
    offset = 0
    while len(collected) < cap:
        data = _get(f"bill/{congress}", sort="updateDate desc", limit=_PAGE, offset=offset)
        items = data.get("bills", []) or []
        if not items:
            break
        for it in items:
            try:
                collected.append(BillListItemRaw.model_validate(it))
            except ValidationError as exc:
                logger.warning("skipping invalid bill list item: %s", exc)
        if not data.get("pagination", {}).get("next"):
            break
        offset += _PAGE
    return collected[:cap]


def _fetch_one(congress: int, bill_type: str, number: int) -> dict | None:
    """Detail + actions + cosponsors for one bill, validated and bundled."""
    lt = bill_type.lower()
    detail = _get(f"bill/{congress}/{lt}/{number}").get("bill")
    if not detail:
        return None
    bill = BillDetailRaw.model_validate(detail).model_dump(mode="json")
    actions = _validate_each(
        _paginate(f"bill/{congress}/{lt}/{number}/actions", "actions"),
        BillActionRaw, f"action for {lt}{number}",
    )
    cosponsors = _validate_each(
        _paginate(f"bill/{congress}/{lt}/{number}/cosponsors", "cosponsors"),
        CosponsorRaw, f"cosponsor for {lt}{number}",
    )
    summaries = _validate_each(
        _paginate(f"bill/{congress}/{lt}/{number}/summaries", "summaries"),
        BillSummaryRaw, f"summary for {lt}{number}",
    )
    text_versions = _validate_each(
        _paginate(f"bill/{congress}/{lt}/{number}/text", "textVersions"),
        BillTextVersionRaw, f"text for {lt}{number}",
    )
    return {
        "bill": bill,
        "actions": actions,
        "cosponsors": cosponsors,
        "summaries": summaries,
        "text_versions": text_versions,
    }


def _stage(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def run() -> int:
    if not settings.congress_gov_api_key:
        raise RuntimeError(
            "CONGRESS_GOV_API_KEY is not set — required for the bills pipeline"
        )
    congress = settings.congress_number
    cap = settings.congress_gov_bill_limit

    listing = _bill_list(congress, cap)
    staged: list[dict] = []
    for item in listing:
        try:
            bundle = _fetch_one(congress, item.type, item.number)
            if bundle:
                staged.append(bundle)
        except Exception as exc:
            # One bad bill shouldn't sink the batch; a systemic failure (bad
            # key, source down) already surfaces on the very first list call.
            logger.warning("skipping bill %s%s: %s", item.type, item.number, exc)

    if not staged:
        raise ValueError("no bills fetched — check the API key and source availability")

    _stage(STAGING_BILLS, staged)
    logger.info(
        "congress_gov_bills: staged %d bills (congress %d, cap %d)",
        len(staged), congress, cap,
    )
    return len(staged)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
