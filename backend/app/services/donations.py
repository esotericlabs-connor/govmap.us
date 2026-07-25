"""On-demand, cached itemized-donations service (Increment 4b).

Backs GET /api/members/{bioguide}/donations. The FEC Schedule A corpus is far
too large to mirror (a single big committee reports 200k+ receipts/cycle), so
this fetches receipts **lazily** as visitors page through a member's ledger and
caches them in `contributions`, keyed by the FEC transaction sub_id (idempotent
dedupe). `donation_fetch` holds the keyset cursor + progress per (member, cycle)
so paging resumes where it left off; once the whole ledger is pulled, every view
serves purely from our DB.

The FEC key is sent as the X-Api-Key header, never a URL param. Without a key (or
a resolvable committee) the endpoint degrades gracefully to whatever is cached
(usually empty) rather than erroring — like the keyed pipelines.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import requests
from sqlalchemy import func, nullslast, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contribution import Contribution, DonationFetch
from app.models.crosswalk import IdCrosswalk
from app.models.member import Member
from app.schemas.finance import ScheduleAItemRaw

logger = logging.getLogger(__name__)

FEC_BASE = "https://api.open.fec.gov/v1"
_TIMEOUT = 30
_MAX_RETRIES = 3
_PER_PAGE = 100  # FEC Schedule A max page size
# Bound per-request latency: cache at most this many pages (×100 rows) on any one
# request. Deeper paging continues on the next request from the stored cursor.
_MAX_PAGES_PER_REQUEST = 8
_CHAMBER_PREFIX = {"house": "H", "senate": "S"}

# Ledger sort options → ORDER BY tuple (sub_id tiebreaks for stability). Default
# is biggest-first, which is the order the on-demand cache is populated in.
_ORDER = {
    "amount": (nullslast(Contribution.amount.desc()), Contribution.sub_id),
    "amount_asc": (nullslast(Contribution.amount.asc()), Contribution.sub_id),
    "date": (nullslast(Contribution.receipt_date.desc()), Contribution.sub_id),
    "date_asc": (nullslast(Contribution.receipt_date.asc()), Contribution.sub_id),
    "name": (nullslast(Contribution.contributor_name.asc()), Contribution.sub_id),
}
_DEFAULT_SORT = "amount"

_session = requests.Session()


def _fec_get(path: str, **params: Any) -> dict:
    """GET one OpenFEC JSON page with light backoff. Errors carry the path only
    (the key is a header), so nothing secret is logged."""
    url = f"{FEC_BASE}/{path}/"
    headers = {"X-Api-Key": settings.fec_api_key}
    last_status = 0
    for attempt in range(1, _MAX_RETRIES + 1):
        resp = _session.get(url, params=params, headers=headers, timeout=_TIMEOUT)
        last_status = resp.status_code
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(min(2**attempt, 10))
            continue
        if not resp.ok:
            body = " ".join(resp.text.split())[:200]
            raise RuntimeError(f"openfec {path} -> HTTP {resp.status_code}: {body}")
        return resp.json()
    raise RuntimeError(f"openfec {path} failing after {_MAX_RETRIES} attempts (HTTP {last_status})")


def _trunc(s: str | None, n: int) -> str | None:
    return s[:n] if s else None


async def _resolve_committee_id(db: AsyncSession, bioguide: str, cycle: int) -> str | None:
    """Resolve a member's principal campaign committee (designation P) via the
    FEC candidate→committees endpoint, using the FEC candidate id from the id
    crosswalk (picked by chamber prefix). Prefers a committee active in `cycle`."""
    member = (
        await db.execute(select(Member.chamber).where(Member.bioguide_id == bioguide))
    ).first()
    if not member:
        return None
    ids = (
        await db.execute(select(IdCrosswalk.fec_ids).where(IdCrosswalk.bioguide_id == bioguide))
    ).first()
    fec_ids = (ids.fec_ids if ids else None) or []
    prefix = _CHAMBER_PREFIX.get(member.chamber)
    candidate_id = next((f for f in fec_ids if prefix and f.startswith(prefix)), None)
    if not candidate_id:
        return None

    data = await asyncio.to_thread(
        _fec_get, f"candidate/{candidate_id}/committees", designation="P", per_page=20
    )
    best: str | None = None
    best_cycle = -1
    for c in data.get("results") or []:
        cid = c.get("committee_id")
        if not cid:
            continue
        cycles = c.get("cycles") or []
        if cycle in cycles:
            return cid
        mx = max(cycles) if cycles else 0
        if mx > best_cycle:
            best_cycle, best = mx, cid
    return best


async def _fetch_more(db: AsyncSession, state: DonationFetch, cycle: int, until: int) -> None:
    """Pull Schedule A pages (biggest receipts first) from the stored cursor and
    cache them, until we've cached `until` rows, the ledger is exhausted, or the
    per-request page cap is hit."""
    committee_id = state.committee_id
    if not committee_id:
        return
    pages = 0
    while not state.complete and state.fetched_count < until and pages < _MAX_PAGES_PER_REQUEST:
        params: dict[str, Any] = {
            "committee_id": committee_id,
            "two_year_transaction_period": cycle,
            "sort": "-contribution_receipt_amount",
            "per_page": _PER_PAGE,
        }
        if state.cursor_index and state.cursor_amount:
            params["last_index"] = state.cursor_index
            params["last_contribution_receipt_amount"] = state.cursor_amount
        try:
            data = await asyncio.to_thread(_fec_get, "schedules/schedule_a", **params)
        except Exception as exc:
            logger.warning("donations: schedule_a fetch failed for %s: %s", committee_id, exc)
            break

        results = data.get("results") or []
        pagination = data.get("pagination") or {}
        if state.total_count is None:
            state.total_count = pagination.get("count")

        rows: list[dict] = []
        for r in results:
            item = ScheduleAItemRaw.model_validate(r)
            if not item.sub_id:
                continue
            rows.append(
                {
                    "sub_id": item.sub_id,
                    "bioguide_id": state.bioguide_id,
                    "committee_id": committee_id,
                    "cycle": cycle,
                    "contributor_name": _trunc(item.contributor_name, 200),
                    "employer": _trunc(item.contributor_employer, 200),
                    "occupation": _trunc(item.contributor_occupation, 200),
                    "city": _trunc(item.contributor_city, 100),
                    "state": _trunc(item.contributor_state, 2),
                    "amount": item.contribution_receipt_amount,
                    "receipt_date": item.contribution_receipt_date,
                    "aggregate_ytd": item.contributor_aggregate_ytd,
                }
            )
        if rows:
            await db.execute(
                pg_insert(Contribution)
                .values(rows)
                .on_conflict_do_nothing(index_elements=[Contribution.sub_id])
            )
            state.fetched_count += len(rows)

        last = pagination.get("last_indexes") or {}
        next_index = last.get("last_index")
        next_amount = last.get("last_contribution_receipt_amount")
        if len(results) < _PER_PAGE or not next_index:
            state.complete = True
        else:
            state.cursor_index = str(next_index)
            state.cursor_amount = None if next_amount is None else str(next_amount)
        pages += 1

    await db.commit()


async def get_donations(
    db: AsyncSession,
    bioguide: str,
    cycle: int,
    offset: int,
    limit: int,
    sort: str = _DEFAULT_SORT,
    q: str | None = None,
) -> dict:
    """A slice of the member's itemized donations ledger, cached on demand from
    the FEC. `sort` reorders and `q` filters (contributor/employer/city) the
    cached rows. Only the default biggest-first view grows the cache (the FEC
    pull is biggest-first); search / alternate sorts run over what's cached."""
    sort = sort if sort in _ORDER else _DEFAULT_SORT
    q = (q or "").strip()
    default_view = not q and sort == _DEFAULT_SORT

    state = await db.get(DonationFetch, (bioguide, cycle))
    if state is None:
        # Race-safe create: two cold first-views of the same member/cycle can't
        # collide on the PK (on_conflict_do_nothing), unlike a plain add+flush.
        await db.execute(
            pg_insert(DonationFetch)
            .values(bioguide_id=bioguide, cycle=cycle)
            .on_conflict_do_nothing(index_elements=[DonationFetch.bioguide_id, DonationFetch.cycle])
        )
        await db.commit()
        state = await db.get(DonationFetch, (bioguide, cycle))
    if state is None:  # pragma: no cover — the row was just ensured to exist
        raise RuntimeError(f"donation_fetch row missing for {bioguide}/{cycle}")

    fec_enabled = bool(settings.fec_api_key)

    # Resolve the principal committee once (retry on a transient failure — resolved
    # stays False so the next request tries again). The FEC call is off-DB, so a
    # failure leaves no DB write to unwind; we just skip ahead and serve cache.
    if fec_enabled and not state.resolved:
        try:
            state.committee_id = await _resolve_committee_id(db, bioguide, cycle)
            state.resolved = True
            await db.commit()
        except Exception as exc:
            logger.warning("donations: committee resolve failed for %s/%s: %s", bioguide, cycle, exc)

    # Only the default biggest-first view grows the cache (the FEC pull walks
    # biggest-first, so it can't cheaply satisfy a filtered/other-sorted window).
    need = offset + limit
    if (
        default_view
        and fec_enabled
        and state.committee_id
        and not state.complete
        and state.fetched_count < need
    ):
        await _fetch_more(db, state, cycle, until=need)

    base = select(Contribution).where(
        Contribution.bioguide_id == bioguide, Contribution.cycle == cycle
    )
    if q:
        like = f"%{q}%"
        base = base.where(
            or_(
                Contribution.contributor_name.ilike(like),
                Contribution.employer.ilike(like),
                Contribution.city.ilike(like),
            )
        )

    # Default view reports the FEC grand total; filtered/sorted views report the
    # count of matching cached rows so pagination stays consistent with results.
    if default_view:
        total = state.total_count
    else:
        total = (
            await db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()

    items = (
        await db.execute(base.order_by(*_ORDER[sort]).limit(limit).offset(offset))
    ).scalars().all()

    return {
        "bioguide_id": bioguide,
        "cycle": cycle,
        "committee_id": state.committee_id,
        "total": total,
        "cached": state.fetched_count,
        "complete": state.complete,
        "sort": sort,
        "q": q or None,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "sub_id": c.sub_id,
                "contributor_name": c.contributor_name,
                "employer": c.employer,
                "occupation": c.occupation,
                "city": c.city,
                "state": c.state,
                "amount": c.amount,
                "date": c.receipt_date.isoformat() if c.receipt_date else None,
                "aggregate_ytd": c.aggregate_ytd,
            }
            for c in items
        ],
    }
