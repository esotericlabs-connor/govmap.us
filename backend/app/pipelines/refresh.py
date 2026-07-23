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

from app.normalize.bills import normalize_and_load as normalize_bills
from app.normalize.committees import load_committees
from app.normalize.crosswalk import load_crosswalk
from app.normalize.members import normalize_and_load
from app.normalize.votes import normalize_and_load as normalize_votes
from app.pipelines import (
    congress_gov_bills,
    congress_legislators,
    house_clerk_votes,
    senate_lis_votes,
)
from app.pipelines.status import record_run

logger = logging.getLogger(__name__)


async def refresh_members() -> None:
    """The congress-legislators source family: one pull (legislators +
    committees + memberships), normalized into members, id_crosswalk,
    committees, and committee_memberships. Order matters — members first
    (crosswalk + memberships FK it), then committees (memberships FK them)."""
    source = "congress_legislators"
    try:
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


# source key -> refresh coroutine. Extended as each source lands.
REFRESHERS: dict[str, callable] = {
    "members": refresh_members,
    "bills": refresh_bills,
    "votes": refresh_votes,
}


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


async def refresh_all() -> list[str]:
    """Run every registered source. One source failing doesn't stop the rest —
    each records its own status. Returns the list of sources that failed so the
    CLI can exit non-zero (a partial load must never pass silently)."""
    failed: list[str] = []
    for name, fn in REFRESHERS.items():
        if not await _run_with_retry(name, fn):
            failed.append(name)
    if failed:
        logger.error("refresh finished WITH FAILURES: %s", ", ".join(failed))
    else:
        logger.info("refresh: all %d source(s) ok", len(REFRESHERS))
    return failed


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    # Non-zero exit on any failure so scripts/deploy.sh surfaces the WARNING
    # (still non-fatal for the deploy — a transient source outage shouldn't
    # block a ship — but never green-and-silent again).
    sys.exit(1 if asyncio.run(refresh_all()) else 0)
