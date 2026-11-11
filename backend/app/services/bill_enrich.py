"""On-demand bill enrichment + in-app full text (Pass 1b).

The `bills` table holds ~250 fully-enriched rows (from the congress_gov_bills
pull) plus ~17k "index" stubs (title + sponsor only) from the sponsored-
legislation pipeline. Rather than a giant up-front backfill, this enriches a
bill **lazily on first view**: `enrich_bill` pulls the Congress.gov detail
bundle (detail + actions + cosponsors + summaries + text) and upserts it, so any
bill a visitor opens becomes rich instantly and stays cached (`enriched_at`).
`get_bill_text` fetches the latest GPO/govinfo "Formatted Text" version and
reduces it to indentation-preserving plain text for in-platform rendering
(cached in `bill_text`). A rolling backfill (pipelines/refresh.py) fills the
long tail over time.

Reuses the pull/normalize helpers so there's one source of truth for the shape
of an enriched bill. Fail-soft: without a Congress.gov key, or on any fetch
failure, the stub is left as-is and retried on the next view.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import date
from urllib.parse import urljoin, urlsplit

import requests
from sqlalchemy import delete, func, nullslast, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session_factory
from app.models.bill import Bill, BillAction, BillText, Cosponsor
from app.normalize.bills import (
    _BILL_UPDATE_COLS,
    _latest_summary,
    _latest_text,
    action_rows,
    cosponsor_rows,
    to_bill_row,
)
from app.pipelines.batch import BatchResult, OutageBreaker
from app.pipelines.congress_gov_bills import _fetch_one, _get
from app.schemas.bill import (
    BillActionRaw,
    BillDetailRaw,
    BillSummaryRaw,
    BillTextVersionRaw,
    CosponsorRaw,
)
from app.services.bounded_http import read_prefix
from app.services.upstream import (
    UpstreamCapacityError,
    UpstreamUnavailableError,
    request_slot,
    run_upstream,
)

logger = logging.getLogger(__name__)

_BILL_ID_RE = re.compile(r"^([a-z]+)(\d+)-(\d+)$")
_TEXT_CAP = 800_000  # chars of plain text to store/serve; huge bills are truncated
_TEXT_TIMEOUT = 30
_TEXT_HOSTS = frozenset({"www.congress.gov", "congress.gov", "www.govinfo.gov", "govinfo.gov"})
_TEXT_MAX_BYTES = 16 * 1024 * 1024  # raw HTML; the largest enrolled bills are a few MB
_TEXT_DEADLINE_SECONDS = 120
_TEXT_MAX_REDIRECTS = 3


def _parse_bill_id(bill_id: str) -> tuple[int, str, int] | None:
    """`hr9578-119` -> (119, 'hr', 9578)."""
    m = _BILL_ID_RE.match(bill_id.strip().lower())
    if not m:
        return None
    return int(m.group(3)), m.group(1), int(m.group(2))


async def enrich_bill(db: AsyncSession, bill_id: str, *, raise_unavailable: bool = False) -> bool:
    """Ensure `bill_id` carries full detail. No-op (one cheap read) if already
    enriched. Returns True once the bill is enriched (now or previously), False
    if it can't be (no key, unknown id, fetch failure — the stub survives).
    `raise_unavailable` lets the batch backfill see a Congress.gov outage (to
    stop early) while visitor requests stay fail-soft."""
    if not settings.congress_gov_api_key:
        return False
    bill = await db.get(Bill, bill_id)
    if bill is None:
        return False
    if bill.enriched_at is not None:
        return True
    parsed = _parse_bill_id(bill_id)
    if parsed is None:
        return False
    congress, btype, number = parsed

    # End the read transaction so no pooled connection is held during the call.
    await db.commit()
    try:
        bundle = await run_upstream("congress", _fetch_one, congress, btype, number)
    except UpstreamCapacityError:
        raise
    except UpstreamUnavailableError:
        if raise_unavailable:
            raise
        logger.warning("bill_enrich: Congress.gov unavailable for %s", bill_id)
        return False
    except Exception as exc:
        logger.warning("bill_enrich: detail fetch failed for %s: %s", bill_id, exc)
        return False
    if not bundle:
        return False

    detail = BillDetailRaw.model_validate(bundle["bill"])
    row = to_bill_row(detail)  # sets enriched_at
    summaries = [BillSummaryRaw.model_validate(s) for s in bundle.get("summaries", [])]
    texts = [BillTextVersionRaw.model_validate(t) for t in bundle.get("text_versions", [])]
    row["summary"], row["summary_date"] = _latest_summary(summaries)
    row["text_url"], row["text_version"] = _latest_text(texts)

    actions = [BillActionRaw.model_validate(a) for a in bundle.get("actions", [])]
    cosponsors = [CosponsorRaw.model_validate(c) for c in bundle.get("cosponsors", [])]
    a_rows = action_rows(bill_id, actions)
    c_rows = cosponsor_rows(bill_id, cosponsors)

    stmt = pg_insert(Bill).values([row])
    update = {c: getattr(stmt.excluded, c) for c in _BILL_UPDATE_COLS}
    update["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=[Bill.bill_id], set_=update)
    await db.execute(stmt)
    # Replace this bill's actions/cosponsors (re-fetched whole).
    await db.execute(delete(BillAction).where(BillAction.bill_id == bill_id))
    if a_rows:
        await db.execute(pg_insert(BillAction).values(a_rows))
    await db.execute(delete(Cosponsor).where(Cosponsor.bill_id == bill_id))
    if c_rows:
        await db.execute(pg_insert(Cosponsor).values(c_rows))
    await db.commit()
    # The Core upsert bypasses the identity map and sessions don't expire on
    # commit, so without this the caller's next SELECT would hand back the stub.
    db.expire(bill)
    logger.info(
        "bill_enrich: enriched %s (%d actions, %d cosponsors)", bill_id, len(a_rows), len(c_rows)
    )
    return True


def _formatted_text_url(versions: list[BillTextVersionRaw]) -> tuple[str | None, str | None]:
    """The URL + label of the newest version that has a human-readable
    'Formatted Text' (HTML) rendition — the one we can turn into in-app text.
    Returns (None, None) when only PDF/XML/no versions exist."""
    for v in sorted(versions, key=lambda x: x.date or date.min, reverse=True):
        fmt = next((f for f in v.formats if f.type == "Formatted Text" and f.url), None)
        if fmt:
            return fmt.url, v.type
    return None, None


def _check_text_url(url: str) -> None:
    """The text URL comes from an upstream payload, so it is only fetched when
    it points at an official bill-text host over HTTPS."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or host not in _TEXT_HOSTS
        or parts.port not in (None, 443)
        or parts.username is not None
    ):
        raise ValueError(f"refusing bill-text URL on host {host!r}")


def _read_capped(resp: requests.Response) -> tuple[str, bool]:
    """Read at most `_TEXT_MAX_BYTES` within `_TEXT_DEADLINE_SECONDS`; returns
    (text, cut_short)."""
    body, cut_short = read_prefix(
        resp,
        max_bytes=_TEXT_MAX_BYTES,
        deadline_s=_TEXT_DEADLINE_SECONDS,
        label="bill text",
    )
    try:
        return body.decode(resp.encoding or "utf-8", errors="replace"), cut_short
    except LookupError:
        return body.decode("utf-8", errors="replace"), cut_short


def _fetch_url(url: str) -> tuple[str, bool]:
    """Fetch a public Congress.gov/GovInfo bill-text page (no API key needed).
    Redirects are followed manually so every hop is re-checked against the
    host allowlist, and the body is size-capped so a misbehaving upstream
    cannot exhaust worker memory. Returns (html, cut_short)."""
    with request_slot("govinfo"):
        for _ in range(_TEXT_MAX_REDIRECTS + 1):
            _check_text_url(url)
            with requests.get(
                url, timeout=_TEXT_TIMEOUT, allow_redirects=False, stream=True
            ) as resp:
                if resp.is_redirect:
                    url = urljoin(url, resp.headers["location"])
                    continue
                resp.raise_for_status()
                return _read_capped(resp)
    raise ValueError("too many redirects fetching bill text")


def _html_to_text(doc: str) -> str:
    """Reduce a bill's 'Formatted Text' HTML to plain text, preserving the
    legislative indentation. GPO wraps the body in <pre> blocks whose whitespace
    IS the layout — keep those verbatim (tags stripped); otherwise fall back to
    turning block-ends into newlines. No HTML reaches the client. A final <pre>
    left open by the fetch size cap still counts.

    Every pass is linear in the input: tag patterns stop at the next "<", and
    trailing whitespace is stripped per line rather than with a backtracking
    regex, so a malformed multi-megabyte body cannot stall the worker."""
    pres = re.findall(r"(?is)<pre[^<>]*>(.*?)(?:</pre>|\Z)", doc)
    if pres:
        body = "\n".join(pres)
    else:
        body = re.sub(r"(?is)<(br|/p|/div|/h[1-6]|/li|/tr)\s*/?>", "\n", doc)
    text = re.sub(r"<[^<>]+>", "", body)
    text = html.unescape(text)
    text = "\n".join(line.rstrip(" \t") for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _text_payload(t: BillText) -> dict:
    return {
        "bill_id": t.bill_id,
        "text_version": t.text_version,
        "source_url": t.source_url,
        "plain": t.plain,
        "truncated": t.truncated,
        "fetched_at": t.fetched_at.isoformat() if t.fetched_at else None,
    }


async def get_bill_text(db: AsyncSession, bill_id: str) -> dict | None:
    """The bill's full legislative text as plain text for in-app rendering,
    cached in `bill_text`. Fetches the latest 'Formatted Text' version on first
    request. Returns None for an unknown bill or one with no readable text
    version (only a PDF, or not yet published)."""
    cached = await db.get(BillText, bill_id)
    if cached is not None:
        return _text_payload(cached)

    bill = await db.get(Bill, bill_id)
    if bill is None or not settings.congress_gov_api_key:
        return None
    parsed = _parse_bill_id(bill_id)
    if parsed is None:
        return None
    congress, btype, number = parsed

    # End the read transaction so no pooled connection is held during either fetch.
    await db.commit()
    try:
        data = await run_upstream("congress", _get, f"bill/{congress}/{btype}/{number}/text")
    except UpstreamCapacityError:
        raise
    except Exception as exc:
        logger.warning("bill_enrich: text-versions fetch failed for %s: %s", bill_id, exc)
        return None
    versions = [BillTextVersionRaw.model_validate(v) for v in (data.get("textVersions") or [])]
    url, version = _formatted_text_url(versions)
    if not url:
        return None

    try:
        html_doc, cut_short = await run_upstream("govinfo", _fetch_url, url)
    except UpstreamCapacityError:
        raise
    except Exception as exc:
        logger.warning("bill_enrich: text-body fetch failed for %s (%s): %s", bill_id, url, exc)
        return None

    plain = await asyncio.to_thread(_html_to_text, html_doc)
    truncated = cut_short or len(plain) > _TEXT_CAP
    if truncated:
        plain = plain[:_TEXT_CAP]

    await db.execute(
        pg_insert(BillText)
        .values(
            bill_id=bill_id,
            text_version=version,
            source_url=url,
            plain=plain,
            truncated=truncated,
        )
        .on_conflict_do_nothing(index_elements=[BillText.bill_id])
    )
    await db.commit()
    row = await db.get(BillText, bill_id)
    return _text_payload(row) if row else None


async def backfill_unenriched(limit: int) -> BatchResult:
    """Enrich up to `limit` not-yet-enriched bills, most-recently-active first
    (they're likeliest to be viewed next). Drives the rolling backfill refresher:
    on-demand enrichment covers what visitors open now; this walks the long tail
    of ~17k sponsored-legislation stubs over successive scheduled runs. Stops
    early once Congress.gov looks down rather than paying a timeout per bill."""
    breaker = OutageBreaker(settings.congress_max_consecutive_failures)
    async with async_session_factory() as db:
        ids = (
            await db.execute(
                select(Bill.bill_id)
                .where(Bill.enriched_at.is_(None))
                .order_by(nullslast(Bill.latest_action_date.desc()), Bill.bill_id)
                .limit(limit)
            )
        ).scalars().all()
        enriched = 0
        failed = 0
        stopped: str | None = None
        for bill_id in ids:
            try:
                ok = await enrich_bill(db, bill_id, raise_unavailable=True)
            except UpstreamCapacityError:
                raise
            except Exception as exc:  # outage, or an unexpected DB error — don't sink the batch
                await db.rollback()
                failed += 1
                logger.warning("bill_enrich: backfill failed for %s: %s", bill_id, exc)
                if breaker.failure(exc):
                    stopped = breaker.reason
                    break
                continue
            breaker.success()
            if ok:
                enriched += 1

    result = BatchResult(total=len(ids), succeeded=enriched, failed=failed, stopped=stopped)
    if stopped is not None and not enriched:
        raise UpstreamUnavailableError("congress", f"backfill enriched nothing; {result.describe('bills')}")
    return result
