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

import logging
import time
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.pipelines.batch import BatchResult, OutageBreaker
from app.pipelines.staging import write_json_atomic
from app.services.bounded_http import read_json
from app.services.upstream import (
    UpstreamCapacityError,
    UpstreamUnavailableError,
    request_slot,
)
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
_TIMEOUT = (10, 30)  # (connect, read) seconds
# A full 250-item page is well under 1 MiB; the deadline covers the body only.
_MAX_BODY_BYTES = 8 * 1024 * 1024
_BODY_DEADLINE_SECONDS = 60

_session = requests.Session()


class IncompleteBillDetailError(RuntimeError):
    """A bill's required child data was capped or failed schema validation."""


def _get(path: str, **params: Any) -> dict:
    """GET one Congress.gov JSON page with backoff on 429/5xx. Errors are raised
    with the path only — never the URL/params — so the API key (sent as a
    header) and query never reach a log or status row.

    A timeout or connection failure — including a body that misses its
    deadline — raises UpstreamUnavailableError at once: retrying would spend
    another full timeout while the source is down, and the batch loops'
    OutageBreaker handles stopping. The body is read inside the request slot so
    the concurrency budget covers the whole transfer."""
    params.setdefault("format", "json")
    url = f"{API_BASE}/{path}"
    headers = {"X-Api-Key": settings.congress_gov_api_key}
    last_status = 0
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with request_slot("congress"):
                resp = _session.get(
                    url, params=params, headers=headers, timeout=_TIMEOUT,
                    stream=True, allow_redirects=False,
                )
                try:
                    status = resp.status_code
                    payload = (
                        read_json(
                            resp,
                            max_bytes=_MAX_BODY_BYTES,
                            deadline_s=_BODY_DEADLINE_SECONDS,
                            label=f"congress.gov {path}",
                        )
                        if 200 <= status < 300
                        else None
                    )
                finally:
                    resp.close()
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise UpstreamUnavailableError("congress", f"{path}: {type(exc).__name__}") from None
        last_status = status
        if status == 429 or status >= 500:
            wait = min(2**attempt, 30)
            logger.warning(
                "congress.gov %s -> HTTP %d; backoff %ds (attempt %d/%d)",
                path, status, wait, attempt, _MAX_RETRIES,
            )
            time.sleep(wait)
            continue
        if payload is None:
            raise RuntimeError(f"congress.gov {path} -> HTTP {status}")
        return payload
    raise UpstreamUnavailableError(
        "congress", f"{path} still failing after {_MAX_RETRIES} attempts (HTTP {last_status})"
    )


def _paginate(path: str, key: str, cap: int = 10**9) -> list[dict]:
    """Follow pagination.next, rejecting any result cap that truncates a bundle."""
    out: list[dict] = []
    offset = 0
    for _ in range(_SUBRESOURCE_MAX_PAGES):
        data = _get(path, limit=_PAGE, offset=offset)
        if not isinstance(data, dict):
            raise IncompleteBillDetailError(f"{path}: child page was not an object")
        items = data.get(key, [])
        pagination = data.get("pagination", {})
        if items is None:
            items = []
        if pagination is None:
            pagination = {}
        if not isinstance(items, list) or not isinstance(pagination, dict):
            raise IncompleteBillDetailError(f"{path}: child page has an invalid shape")
        out.extend(items)
        next_page = pagination.get("next")
        if next_page is not None and not isinstance(next_page, str):
            raise IncompleteBillDetailError(f"{path}: child pagination link has an invalid shape")
        has_next = bool(next_page)
        if len(out) > cap or (len(out) >= cap and has_next):
            raise IncompleteBillDetailError(
                f"{path}: child result cap reached before pagination completed"
            )
        if not has_next:
            break
        offset += _PAGE
    else:
        raise IncompleteBillDetailError(
            f"{path}: child pagination exceeded {_SUBRESOURCE_MAX_PAGES} pages"
        )
    return out[:cap]


def _validate_each(records: list, model: type[BaseModel], label: str) -> list[dict]:
    """Validate every child row; a rejected row makes the bill bundle incomplete."""
    valid: list[dict] = []
    for record in records:
        try:
            valid.append(model.model_validate(record).model_dump(mode="json"))
        except ValidationError as exc:
            raise IncompleteBillDetailError(
                f"invalid {label} payload; refusing an incomplete bill bundle"
            ) from exc
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
    write_json_atomic(path, data, indent=2)


def run() -> BatchResult:
    """Pull, validate, and stage the bill batch. Bounded by a wall-clock budget
    and an OutageBreaker; whatever was fetched before an early stop is still
    staged, which is safe because the normalizer upserts per bill."""
    if not settings.congress_gov_api_key:
        raise RuntimeError(
            "CONGRESS_GOV_API_KEY is not set — required for the bills pipeline"
        )
    congress = settings.congress_number
    cap = settings.congress_gov_bill_limit
    budget = settings.congress_gov_bills_max_seconds
    deadline = time.monotonic() + budget
    breaker = OutageBreaker(settings.congress_max_consecutive_failures)

    listing = _bill_list(congress, cap)
    staged: list[dict] = []
    failed = 0
    incomplete = 0
    stopped: str | None = None
    for item in listing:
        if time.monotonic() >= deadline:
            stopped = f"{budget}s time budget reached"
            break
        try:
            bundle = _fetch_one(congress, item.type, item.number)
        except UpstreamCapacityError:
            raise
        except Exception as exc:
            failed += 1
            if isinstance(exc, IncompleteBillDetailError):
                incomplete += 1
            logger.warning("skipping bill %s%s: %s", item.type, item.number, exc)
            if breaker.failure(exc):
                stopped = breaker.reason
                break
            continue
        breaker.success()
        if bundle:
            staged.append(bundle)

    result = BatchResult(
        total=len(listing),
        succeeded=len(staged),
        failed=failed,
        stopped=stopped,
        incomplete=incomplete > 0,
    )
    if not staged:
        if stopped is not None:
            raise UpstreamUnavailableError("congress", f"no bills fetched; {result.describe('bills')}")
        raise ValueError("no bills fetched — check the API key and source availability")

    _stage(STAGING_BILLS, staged)
    detail = result.describe("bills")
    logger.info(
        "congress_gov_bills: staged %d bills (congress %d, cap %d)%s",
        len(staged), congress, cap, f" — {detail}" if detail else "",
    )
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
