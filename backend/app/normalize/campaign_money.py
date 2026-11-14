"""Layer 2: atomically load exact FEC candidate and committee-link snapshots."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_factory
from app.models.campaign_money import (
    CampaignMoneyCoverage,
    CandidateCommitteeLink,
    CandidateFinanceSummary,
)
from app.normalize.dates import normalize_date
from app.pipelines.fec_candidate_totals import STAGING_PATH, snapshot_revision
from app.schemas.campaign_money import FecCampaignMoneySnapshotRaw

logger = logging.getLogger(__name__)
_CHUNK = 500


async def load_campaign_money(path: Path = STAGING_PATH) -> int:
    if not path.exists():
        raise FileNotFoundError(f"no candidate finance staging data at {path}")
    try:
        staged = FecCampaignMoneySnapshotRaw.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise ValueError("FEC candidate finance staging snapshot is invalid") from exc

    if not staged.complete:
        raise ValueError("refusing to load an incomplete FEC finance snapshot")
    if staged.candidate_count != len(staged.candidates) or staged.linkage_count != len(staged.linkages):
        raise ValueError("FEC finance staging counts do not match the snapshot")
    if len({row.candidate_id for row in staged.candidates}) != len(staged.candidates):
        raise ValueError("FEC finance staging contains duplicate candidate IDs")
    if len({row.linkage_id for row in staged.linkages}) != len(staged.linkages):
        raise ValueError("FEC finance staging contains duplicate linkage IDs")
    if any(row.fec_election_year != staged.finance_cycle for row in staged.linkages):
        raise ValueError("FEC finance staging contains a linkage from another cycle")
    if any(row.office != row.candidate_id[0] for row in staged.candidates):
        raise ValueError("FEC candidate IDs do not match their reported offices")
    if snapshot_revision(staged.candidates, staged.linkages) != staged.snapshot_revision:
        raise ValueError("FEC finance staging snapshot revision does not match its content")

    candidates = []
    for candidate in staged.candidates:
        row = candidate.model_dump()
        row["coverage_end"] = normalize_date(candidate.coverage_end)
        row["finance_cycle"] = staged.finance_cycle
        candidates.append(row)
    linkages = [
        {**linkage.model_dump(), "finance_cycle": staged.finance_cycle}
        for linkage in staged.linkages
    ]
    coverage = {
        "finance_cycle": staged.finance_cycle,
        "complete": True,
        "candidate_count": len(candidates),
        "linkage_count": len(linkages),
        "summary_sha256": staged.summary_file.sha256,
        "summary_last_modified": staged.summary_file.last_modified,
        "linkage_sha256": staged.linkage_file.sha256,
        "linkage_last_modified": staged.linkage_file.last_modified,
        "snapshot_revision": staged.snapshot_revision,
        "fetched_at": staged.fetched_at,
    }

    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                delete(CandidateFinanceSummary).where(
                    CandidateFinanceSummary.finance_cycle == staged.finance_cycle
                )
            )
            await session.execute(
                delete(CandidateCommitteeLink).where(
                    CandidateCommitteeLink.finance_cycle == staged.finance_cycle
                )
            )
            for start in range(0, len(candidates), _CHUNK):
                await session.execute(
                    pg_insert(CandidateFinanceSummary).values(candidates[start : start + _CHUNK])
                )
            for start in range(0, len(linkages), _CHUNK):
                await session.execute(
                    pg_insert(CandidateCommitteeLink).values(linkages[start : start + _CHUNK])
                )
            statement = pg_insert(CampaignMoneyCoverage).values(coverage)
            statement = statement.on_conflict_do_update(
                index_elements=[CampaignMoneyCoverage.finance_cycle],
                set_={
                    key: getattr(statement.excluded, key)
                    for key in coverage
                    if key != "finance_cycle"
                },
            )
            await session.execute(statement)

    logger.info(
        "campaign_money: atomically replaced %d candidates and %d linkages for cycle %d",
        len(candidates),
        len(linkages),
        staged.finance_cycle,
    )
    return len(candidates)


if __name__ == "__main__":
    asyncio.run(load_campaign_money())
