"""On-demand, cached itemized-donations service (Increment 4b).

Backs GET /api/members/{bioguide}/donations. The FEC Schedule A corpus is far
too large to mirror (a single big committee reports 200k+ receipts/cycle), so
this fetches receipts **lazily** as visitors page through a member's ledger and
caches them in `contributions`, keyed by the FEC source-row sub_id for
idempotent replay. This does not reconcile amendments or establish distinct
contributions. `donation_fetch` holds the keyset cursor + progress per
(member, cycle) so paging resumes where it left off; reaching a terminal cursor
does not establish complete or current economic-contribution coverage.

The FEC key is sent as the X-Api-Key header, never a URL param. Without a key (or
a resolvable committee) the endpoint degrades gracefully to whatever is cached
(usually empty) rather than erroring — like the keyed pipelines.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, cast

import requests
from sqlalchemy import func, nullslast, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contribution import Contribution, DonationFetch
from app.models.crosswalk import IdCrosswalk
from app.models.finance import MemberFinance
from app.models.member import Member
from app.schemas.finance import ScheduleAPageRaw
from app.services.bounded_http import read_body, text_excerpt
from app.services.search import LIKE_ESCAPE, substring_pattern
from app.services.upstream import UpstreamCapacityError, request_slot, run_upstream

logger = logging.getLogger(__name__)

FEC_BASE = "https://api.open.fec.gov/v1"
_TIMEOUT = 30
_MAX_RETRIES = 3
# A 100-receipt Schedule A page is a few hundred KiB; the deadline covers the
# body only and stays short because a visitor's request is waiting on it.
_MAX_BODY_BYTES = 8 * 1024 * 1024
_BODY_DEADLINE_SECONDS = 30
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
        with request_slot("fec"):
            resp = _session.get(
                url, params=params, headers=headers, timeout=_TIMEOUT,
                stream=True, allow_redirects=False,
            )
            try:
                status = resp.status_code
                body = read_body(
                    resp,
                    max_bytes=_MAX_BODY_BYTES,
                    deadline_s=_BODY_DEADLINE_SECONDS,
                    label=f"openfec {path}",
                )
            finally:
                resp.close()
        last_status = status
        if status == 429 or status >= 500:
            time.sleep(min(2**attempt, 10))
            continue
        if status >= 300:
            raise RuntimeError(f"openfec {path} -> HTTP {status}: {text_excerpt(body, 200)}")
        return json.loads(body)
    raise RuntimeError(f"openfec {path} failing after {_MAX_RETRIES} attempts (HTTP {last_status})")


def _trunc(s: str | None, n: int) -> str | None:
    return s[:n] if s else None


async def _resolve_candidate_id(db: AsyncSession, bioguide: str) -> str | None:
    """The member's current-office FEC candidate id (S… senators / H… reps), read
    from the id crosswalk and picked by chamber prefix."""
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
    return next((f for f in fec_ids if prefix and f.startswith(prefix)), None)


async def _principal_committee_id(candidate_id: str, cycle: int) -> str | None:
    """Resolve a candidate's principal campaign committee (designation P) via the
    FEC candidate→committees endpoint. Prefers a committee active in `cycle`.
    Network only — callers must not hold a database transaction open across it."""
    data = await run_upstream(
        "fec", _fec_get, f"candidate/{candidate_id}/committees", designation="P", per_page=20
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


async def get_donation_cycles(db: AsyncSession, bioguide: str) -> list[int]:
    """The two-year cycles a member's itemized donations can be browsed for, newest
    first — the union of every principal committee's `cycles` on the FEC, plus any
    cycle we already hold a finance summary for and the configured current cycle
    (so the picker always offers 'now'). Fail-soft: with no FEC key / no candidate
    / an FEC error it returns just what we can derive locally."""
    cycles: set[int] = set(
        (
            await db.execute(
                select(MemberFinance.cycle).where(MemberFinance.bioguide_id == bioguide)
            )
        ).scalars().all()
    )
    cycles.add(settings.fec_cycle)

    candidate_id = await _resolve_candidate_id(db, bioguide) if settings.fec_api_key else None
    if candidate_id:
        # End the read transaction so no pooled connection idles in a
        # transaction while the FEC answers.
        await db.commit()
        try:
            data = await run_upstream(
                "fec", _fec_get, f"candidate/{candidate_id}/committees", designation="P", per_page=20
            )
            for c in data.get("results") or []:
                for cy in c.get("cycles") or []:
                    if isinstance(cy, int):
                        cycles.add(cy)
        except UpstreamCapacityError:
            raise
        except Exception as exc:
            logger.warning("donations: cycle list fetch failed for %s: %s", bioguide, exc)

    return sorted(cycles, reverse=True)


async def _reload_progress(db: AsyncSession, state: DonationFetch, cycle: int) -> None:
    """Copy the committed cursor/progress onto the detached `state` snapshot."""
    row = (
        await db.execute(
            select(
                DonationFetch.fetched_count,
                DonationFetch.total_count,
                DonationFetch.complete,
                DonationFetch.cursor_index,
                DonationFetch.cursor_amount,
            ).where(
                DonationFetch.bioguide_id == state.bioguide_id,
                DonationFetch.cycle == cycle,
            )
        )
    ).one()
    for key, value in row._mapping.items():
        setattr(state, key, value)


async def _fetch_more(db: AsyncSession, state: DonationFetch, cycle: int, until: int) -> None:
    """Pull Schedule A pages (biggest receipts first) from the stored cursor and
    cache them, until we've cached `until` rows, the ledger is exhausted, or the
    per-request page cap is hit.

    Callers pass a `state` detached from `db` with no transaction open, so each
    FEC request runs outside any transaction. A page's receipts and its advanced
    cursor then commit together only if no concurrent request moved the cursor
    first (compare-and-set). A losing request discards its page and adopts the
    committed progress, so the cursor never regresses or mixes two requests'
    keyset values."""
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
            data = await run_upstream("fec", _fec_get, "schedules/schedule_a", **params)
        except UpstreamCapacityError:
            raise
        except Exception as exc:
            logger.warning("donations: schedule_a fetch failed for %s: %s", committee_id, exc)
            break

        try:
            page = ScheduleAPageRaw.model_validate(data)
            last = page.pagination.last_indexes
            next_index = None if last.last_index is None else str(last.last_index)
            next_amount = last.last_contribution_receipt_amount
            complete = len(page.results) < _PER_PAGE
            if not complete and (
                not next_index
                or next_amount is None
                or next_index == state.cursor_index
            ):
                raise ValueError("missing or repeated Schedule A cursor")
        except ValueError as exc:
            # Do not publish a page or advance past unvalidated receipts.
            logger.warning(
                "donations: invalid schedule_a page for %s (%s); keeping cached progress",
                committee_id,
                type(exc).__name__,
            )
            break

        rows: list[dict] = []
        for item in page.results:
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

        inserted_count = 0
        if rows:
            inserted = await db.execute(
                pg_insert(Contribution)
                .values(rows)
                .on_conflict_do_nothing(index_elements=[Contribution.sub_id])
                .returning(Contribution.sub_id)
            )
            inserted_count = len(inserted.scalars().all())

        progress: dict[str, Any] = {
            "fetched_count": state.fetched_count + inserted_count,
            "total_count": (
                state.total_count if state.total_count is not None else page.pagination.count
            ),
            "complete": complete,
            "cursor_index": state.cursor_index if complete else str(next_index),
            "cursor_amount": (
                state.cursor_amount
                if complete
                else (None if next_amount is None else str(next_amount))
            ),
        }
        if complete and progress["fetched_count"] < page.pagination.count:
            await db.rollback()
            logger.warning(
                "donations: truncated schedule_a page for %s; keeping cached progress",
                committee_id,
            )
            break

        advanced = cast(
            CursorResult[Any],
            await db.execute(
                update(DonationFetch)
                .where(
                    DonationFetch.bioguide_id == state.bioguide_id,
                    DonationFetch.cycle == cycle,
                    DonationFetch.complete.is_(False),
                    DonationFetch.fetched_count == state.fetched_count,
                    DonationFetch.cursor_index.is_not_distinct_from(state.cursor_index),
                    DonationFetch.cursor_amount.is_not_distinct_from(state.cursor_amount),
                )
                .values(**progress)
                .execution_options(synchronize_session=False)
            ),
        )
        if advanced.rowcount != 1:
            await db.rollback()
            await _reload_progress(db, state, cycle)
            logger.info(
                "donations: %s/%s cursor advanced concurrently; serving committed progress",
                state.bioguide_id,
                cycle,
            )
            return
        await db.commit()
        for key, value in progress.items():
            setattr(state, key, value)
        pages += 1


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
    # stays False so the next request tries again). The local candidate lookup
    # commits before the FEC call so no transaction stays open across it; a
    # failure leaves no DB write to unwind, so we just skip ahead and serve cache.
    if fec_enabled and not state.resolved:
        candidate_id = await _resolve_candidate_id(db, bioguide)
        await db.commit()
        try:
            committee_id = (
                await _principal_committee_id(candidate_id, cycle) if candidate_id else None
            )
        except UpstreamCapacityError:
            raise
        except Exception as exc:
            logger.warning("donations: committee resolve failed for %s/%s: %s", bioguide, cycle, exc)
        else:
            state.committee_id = committee_id
            state.resolved = True
            await db.commit()

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
        # _fetch_more persists progress only through compare-and-set updates, so
        # it works on a detached snapshot and starts with no transaction open.
        await db.commit()
        db.expunge(state)
        await _fetch_more(db, state, cycle, until=need)

    base = select(Contribution).where(
        Contribution.bioguide_id == bioguide, Contribution.cycle == cycle
    )
    if q:
        like = substring_pattern(q)
        base = base.where(
            or_(
                Contribution.contributor_name.ilike(like, escape=LIKE_ESCAPE),
                Contribution.employer.ilike(like, escape=LIKE_ESCAPE),
                Contribution.city.ilike(like, escape=LIKE_ESCAPE),
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
