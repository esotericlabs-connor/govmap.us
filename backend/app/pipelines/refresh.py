"""Per-source refresh orchestration: pull -> normalize -> record status.

The single entry point both the scheduler and manual/deploy runs call, so
pipeline_status stays consistent no matter how a refresh is triggered. Add a
new source by writing its refresh_* coroutine and registering it in REFRESHERS.

Run directly: `python -m app.pipelines.refresh` (refreshes every source) — this
is what scripts/deploy.sh invokes.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.db import async_session_factory
from app.models.member import Member
from app.normalize.bills import normalize_and_load as normalize_bills
from app.normalize.committee_meetings import load_committee_meetings
from app.normalize.committees import load_committees
from app.normalize.crosswalk import load_crosswalk
from app.normalize.finance import load_finance
from app.normalize.member_sponsored import load_member_sponsored
from app.normalize.members import normalize_and_load
from app.normalize.votes import normalize_and_load as normalize_votes
from app.normalize.zip_districts import load_zip_districts
from app.pipelines import (
    congress_committee_meetings,
    congress_gov_bills,
    congress_legislators,
    congress_member_sponsored,
    fec_finance,
    house_clerk_votes,
    senate_lis_votes,
    zip_crosswalk,
)
from app.pipelines.status import record_run, send_alert
from app.services.bill_enrich import backfill_unenriched

logger = logging.getLogger(__name__)

_SEAT_CHANGE_LIST_CAP = 12


async def _held_house_districts() -> set[str]:
    """The set of currently-held House seats, keyed like the map (STATE-DISTRICT,
    at-large = STATE-0). A district absent from this set is vacant."""
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(Member.state, Member.district).where(Member.chamber == "house")
            )
        ).all()
    return {f"{state}-{district if district is not None else 0}" for state, district in rows}


async def _alert_seat_changes(before: set[str], after: set[str]) -> None:
    """Notify (log + webhook) when House seats flip vacant<->filled between roster
    refreshes — e.g. a special-election winner being seated. Skips the very first
    load (empty `before`) so we don't alert on all 435 seats at once."""
    if not before:
        return
    for label, changed in (
        ("newly filled", sorted(after - before)),
        ("newly vacant", sorted(before - after)),
    ):
        if not changed:
            continue
        shown = ", ".join(changed[:_SEAT_CHANGE_LIST_CAP])
        overflow = len(changed) - _SEAT_CHANGE_LIST_CAP
        extra = f" (+{overflow} more)" if overflow > 0 else ""
        msg = f"GovMap: {len(changed)} House seat(s) {label} — {shown}{extra}"
        logger.info(msg)
        await send_alert(msg)


async def refresh_members() -> None:
    """The congress-legislators source family: one pull (legislators +
    committees + memberships), normalized into members, id_crosswalk,
    committees, and committee_memberships. Order matters — members first
    (crosswalk + memberships FK it), then committees (memberships FK them)."""
    source = "congress_legislators"
    try:
        held_before = await _held_house_districts()
        # The pull is synchronous (requests) — run it off the event loop.
        await asyncio.to_thread(congress_legislators.run)
        count = await normalize_and_load()
        await load_crosswalk()
        await load_committees()
        await record_run(source, count, "ok")
        logger.info("refresh %s: ok (%d members + crosswalk + committees)", source, count)
    except Exception as exc:
        await record_run(source, 0, "error", str(exc))
        logger.exception("refresh %s failed", source)
        raise
    # Roster refreshed + status recorded. Surface any seat that flipped vacant<->
    # filled. Best-effort: a hiccup here must never fail an otherwise-good refresh.
    try:
        await _alert_seat_changes(held_before, await _held_house_districts())
    except Exception:
        logger.warning("refresh %s: seat-change check failed", source, exc_info=True)


async def refresh_bills() -> None:
    """Congress.gov bills: pull the most-recently-updated current-Congress bills
    (detail + actions + cosponsors) and normalize into bills/bill_actions/
    cosponsors. Independent of refresh_members — no shared FKs (sponsor/
    cosponsor bioguide columns are unenforced), so it can run in any order."""
    source = "congress_gov_bills"
    try:
        await asyncio.to_thread(congress_gov_bills.run)
        count = await normalize_bills()
        await record_run(source, count, "ok")
        logger.info("refresh %s: ok (%d bills + actions + cosponsors)", source, count)
    except Exception as exc:
        await record_run(source, 0, "error", str(exc))
        logger.exception("refresh %s failed", source)
        raise


async def refresh_votes() -> None:
    """Roll-call votes from two chambers/sources (House Clerk XML + Senate LIS
    XML), normalized together. The two pulls are independent — one chamber's
    source being down still loads the other (recorded as 'partial'); only both
    failing raises (so the retry/visibility framework kicks in). Senate positions
    resolve LIS->Bioguide via id_crosswalk in the normalizer."""
    source = "votes"
    failed: list[str] = []
    try:
        for name, fn in (("house", house_clerk_votes.run), ("senate", senate_lis_votes.run)):
            try:
                await asyncio.to_thread(fn)
            except Exception as exc:
                failed.append(name)
                logger.warning("votes: %s pull failed: %s", name, exc)
        if len(failed) == 2:
            raise RuntimeError("both House and Senate vote pulls failed")
        count = await normalize_votes()
        status = "ok" if not failed else "partial"
        detail = None if not failed else f"chamber(s) failed: {', '.join(failed)}"
        await record_run(source, count, status, detail)
        logger.info("refresh votes: %s (%d votes; failed: %s)", status, count, failed or "none")
    except Exception as exc:
        await record_run(source, 0, "error", str(exc))
        logger.exception("refresh %s failed", source)
        raise


async def refresh_sponsored_bills() -> None:
    """Per-member sponsored legislation → complete sponsored-bill coverage for
    the current Congress. Reads the legislators staging file (so refresh_members
    should have run first) and upserts index rows into `bills`. Independent of
    refresh_bills — the upsert is on bill_id and doesn't touch the enriched
    actions/cosponsors."""
    source = "member_sponsored"
    try:
        await asyncio.to_thread(congress_member_sponsored.run)
        count = await load_member_sponsored()
        await record_run(source, count, "ok")
        logger.info("refresh %s: ok (%d sponsored bills)", source, count)
    except Exception as exc:
        await record_run(source, 0, "error", str(exc))
        logger.exception("refresh %s failed", source)
        raise


async def refresh_finance() -> None:
    """FEC campaign-finance totals per member. Reads the legislators staging file
    for FEC candidate ids (so refresh_members should have run first) and upserts
    into member_finance. Requires FEC_API_KEY — without it this records a
    non-fatal error (like the bills pipeline without a Congress.gov key)."""
    source = "fec_finance"
    try:
        await asyncio.to_thread(fec_finance.run)
        count = await load_finance()
        await record_run(source, count, "ok")
        logger.info("refresh %s: ok (%d finance rows)", source, count)
    except Exception as exc:
        await record_run(source, 0, "error", str(exc))
        logger.exception("refresh %s failed", source)
        raise


async def refresh_committee_meetings() -> None:
    """Committee meetings from Congress.gov (detail per event) → committee_meetings.
    Independent of the other sources except the committees FK, so refresh_members
    should have run first (it does, on every deploy). Full-replace load."""
    source = "committee_meetings"
    try:
        await asyncio.to_thread(congress_committee_meetings.run)
        count = await load_committee_meetings()
        await record_run(source, count, "ok")
        logger.info("refresh %s: ok (%d meetings)", source, count)
    except Exception as exc:
        await record_run(source, 0, "error", str(exc))
        logger.exception("refresh %s failed", source)
        raise


async def refresh_backfill_bills() -> None:
    """Rolling enrichment of the sponsored-legislation "stub" bills: each run
    enriches the next batch of not-yet-enriched bills (actions + cosponsors +
    summary + text link), most-recently-active first, so the full ~17k corpus
    fills in over successive scheduled runs. On-demand enrichment (routers/bills)
    already covers any bill a visitor opens; this walks the long tail. Bounded
    per run (bills_backfill_per_run) to stay under the Congress.gov rate limit."""
    source = "backfill_bills"
    try:
        count = await backfill_unenriched(settings.bills_backfill_per_run)
        await record_run(source, count, "ok")
        logger.info("refresh %s: ok (%d bills enriched this run)", source, count)
    except Exception as exc:
        await record_run(source, 0, "error", str(exc))
        logger.exception("refresh %s failed", source)
        raise


async def refresh_zip_districts() -> None:
    """ZIP→congressional-district crosswalk from the Census ZCTA↔CD relationship
    file. Rare-change data (moves only on redistricting), but cheap to reload;
    a full replace keeps stale mappings from lingering. Independent of the other
    sources — no shared FKs."""
    source = "zip_districts"
    try:
        await asyncio.to_thread(zip_crosswalk.run)
        count = await load_zip_districts()
        await record_run(source, count, "ok")
        logger.info("refresh %s: ok (%d ZIP→district rows)", source, count)
    except Exception as exc:
        await record_run(source, 0, "error", str(exc))
        logger.exception("refresh %s failed", source)
        raise


# Fast / essential sources refreshed on EVERY deploy (the CLI default). Each is
# a modest, well-behaved pull, so the deploy stays quick.
CORE_REFRESHERS: dict[str, callable] = {
    "members": refresh_members,
    "bills": refresh_bills,
    "votes": refresh_votes,
}

# Heavier / slow-cadence / rate-limited sources kept OFF the deploy hot path:
# each makes hundreds of third-party calls (and FEC is throttled to ~1000/hr),
# so running them on every redeploy exhausts API budgets and drags the deploy
# out. They run on their own scheduler cadence (see app/scheduler.py) and on
# demand, e.g.:  docker compose exec backend python -m app.pipelines.refresh finance
# (member_sponsored reads the legislators staging that refresh_members writes, so
# a members refresh must have run first — it does, on every deploy.)
EXTRA_REFRESHERS: dict[str, callable] = {
    "sponsored_bills": refresh_sponsored_bills,
    "finance": refresh_finance,
    "zip_districts": refresh_zip_districts,
    "committee_meetings": refresh_committee_meetings,
    "backfill_bills": refresh_backfill_bills,
}

# Full registry (deploy core + extras) — the target for a manual `refresh all`.
REFRESHERS: dict[str, callable] = {**CORE_REFRESHERS, **EXTRA_REFRESHERS}


async def _run_with_retry(name: str, fn, retries: int = 2, delay: float = 5.0) -> bool:
    """Run one source, retrying transient failures (a DB/connection blip right
    after a migration is the likely culprit behind a partial deploy load).
    Returns True on success."""
    for attempt in range(1, retries + 2):
        try:
            await fn()
            return True
        except Exception:
            if attempt <= retries:
                logger.warning("refresh '%s' failed (attempt %d) — retrying in %ss", name, attempt, delay)
                await asyncio.sleep(delay)
            else:
                logger.exception("refresh '%s' failed after %d attempts", name, attempt)
    return False


async def run_refreshers(targets: dict[str, callable]) -> list[str]:
    """Run the given sources. One failing doesn't stop the rest — each records
    its own status. Returns the failed source names so the CLI can exit non-zero
    (a partial load must never pass silently)."""
    failed: list[str] = []
    for name, fn in targets.items():
        if not await _run_with_retry(name, fn):
            failed.append(name)
    if failed:
        logger.error("refresh finished WITH FAILURES: %s", ", ".join(failed))
    else:
        logger.info("refresh: all %d source(s) ok", len(targets))
    return failed


async def refresh_all() -> list[str]:
    """Every registered source (core + extras). Used by a manual `refresh all`;
    the scheduler runs each source on its own cadence instead."""
    return await run_refreshers(REFRESHERS)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    # Usage:
    #   python -m app.pipelines.refresh            # deploy default: CORE only
    #   python -m app.pipelines.refresh all        # every source (core + extras)
    #   python -m app.pipelines.refresh finance …  # named source(s), on demand
    args = sys.argv[1:]
    if not args:
        targets = CORE_REFRESHERS
    elif args == ["all"]:
        targets = REFRESHERS
    else:
        unknown = [a for a in args if a not in REFRESHERS]
        if unknown:
            sys.exit(
                f"unknown refresher(s): {', '.join(unknown)} — "
                f"choose from {', '.join(REFRESHERS)}, or 'all'"
            )
        targets = {a: REFRESHERS[a] for a in args}

    # Non-zero exit on any failure so scripts/deploy.sh surfaces the WARNING
    # (still non-fatal for the deploy — a transient source outage shouldn't
    # block a ship — but never green-and-silent again).
    sys.exit(1 if asyncio.run(run_refreshers(targets)) else 0)
