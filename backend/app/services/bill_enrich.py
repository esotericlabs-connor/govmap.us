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

import requests
from sqlalchemy import delete, nullslast, select
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
from app.pipelines.congress_gov_bills import _fetch_one, _get
from app.schemas.bill import (
    BillActionRaw,
    BillDetailRaw,
    BillSummaryRaw,
    BillTextVersionRaw,
    CosponsorRaw,
)

logger = logging.getLogger(__name__)

_BILL_ID_RE = re.compile(r"^([a-z]+)(\d+)-(\d+)$")
_TEXT_CAP = 800_000  # chars of plain text to store/serve; huge bills are truncated
_TEXT_TIMEOUT = 30


def _parse_bill_id(bill_id: str) -> tuple[int, str, int] | None:
    """`hr9578-119` -> (119, 'hr', 9578)."""
    m = _BILL_ID_RE.match(bill_id.strip().lower())
    if not m:
        return None
    return int(m.group(3)), m.group(1), int(m.group(2))


async def enrich_bill(db: AsyncSession, bill_id: str) -> bool:
    """Ensure `bill_id` carries full detail. No-op (one cheap read) if already
    enriched. Returns True once the bill is enriched (now or previously), False
    if it can't be (no key, unknown id, fetch failure — the stub survives)."""
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

    try:
        bundle = await asyncio.to_thread(_fetch_one, congress, btype, number)
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


def _fetch_url(url: str) -> str:
    """Fetch a public GPO/govinfo text page (no API key needed)."""
    resp = requests.get(url, timeout=_TEXT_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _html_to_text(doc: str) -> str:
    """Reduce a bill's 'Formatted Text' HTML to plain text, preserving the
    legislative indentation. GPO wraps the body in <pre> blocks whose whitespace
    IS the layout — keep those verbatim (tags stripped); otherwise fall back to
    turning block-ends into newlines. No HTML reaches the client."""
    pres = re.findall(r"(?is)<pre[^>]*>(.*?)</pre>", doc)
    if pres:
        body = "\n".join(pres)
    else:
        body = re.sub(r"(?is)<(br|/p|/div|/h[1-6]|/li|/tr)\s*/?>", "\n", doc)
    text = re.sub(r"(?s)<[^>]+>", "", body)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
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

    try:
        data = await asyncio.to_thread(_get, f"bill/{congress}/{btype}/{number}/text")
    except Exception as exc:
        logger.warning("bill_enrich: text-versions fetch failed for %s: %s", bill_id, exc)
        return None
    versions = [BillTextVersionRaw.model_validate(v) for v in (data.get("textVersions") or [])]
    url, version = _formatted_text_url(versions)
    if not url:
        return None

    try:
        html_doc = await asyncio.to_thread(_fetch_url, url)
    except Exception as exc:
        logger.warning("bill_enrich: text-body fetch failed for %s (%s): %s", bill_id, url, exc)
        return None

    plain = _html_to_text(html_doc)
    truncated = len(plain) > _TEXT_CAP
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


async def backfill_unenriched(limit: int) -> int:
    """Enrich up to `limit` not-yet-enriched bills, most-recently-active first
    (they're likeliest to be viewed next). Drives the rolling backfill refresher:
    on-demand enrichment covers what visitors open now; this walks the long tail
    of ~17k sponsored-legislation stubs over successive scheduled runs. Returns
    how many were enriched this run."""
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
        for bill_id in ids:
            try:
                if await enrich_bill(db, bill_id):
                    enriched += 1
            except Exception as exc:  # unexpected DB error — don't sink the batch
                await db.rollback()
                logger.warning("bill_enrich: backfill failed for %s: %s", bill_id, exc)
        return enriched
