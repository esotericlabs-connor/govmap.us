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

from app.normalize.committees import load_committees
from app.normalize.crosswalk import load_crosswalk
from app.normalize.members import normalize_and_load
from app.pipelines import congress_legislators
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


# source key -> refresh coroutine. Extended as each source lands.
REFRESHERS: dict[str, callable] = {
    "members": refresh_members,
}


async def refresh_all() -> None:
    """Run every registered source. One source failing doesn't stop the rest —
    each records its own status."""
    for name, fn in REFRESHERS.items():
        try:
            await fn()
        except Exception:
            logger.exception("refresh '%s' errored (continuing with others)", name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(refresh_all())
