"""Layer 2 normalizer: complete OpenFEC candidate snapshot -> Postgres."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_factory
from app.models.election import ElectionCandidate, ElectionCatalogCoverage
from app.normalize.dates import normalize_date
from app.schemas.election import FecCandidateRaw, FecCandidateSnapshotRaw

logger = logging.getLogger(__name__)

STAGING_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "staging" / "fec_candidates_raw.json"
)
_CHUNK = 500


def _candidate_row(finance_cycle: int, candidate: FecCandidateRaw) -> dict:
    return {
        "finance_cycle": finance_cycle,
        "candidate_id": candidate.candidate_id,
        "name": candidate.name,
        "office": candidate.office,
        "office_full": candidate.office_full,
        "state": candidate.state,
        "district": candidate.district,
        "party": candidate.party,
        "party_full": candidate.party_full,
        "candidate_status": candidate.candidate_status,
        "incumbent_challenge": candidate.incumbent_challenge,
        "first_file_date": normalize_date(candidate.first_file_date),
        "last_file_date": normalize_date(candidate.last_file_date),
        "cycles": candidate.cycles or [],
        "election_years": candidate.election_years or [],
        "principal_committees": [
            committee.model_dump(mode="json")
            for committee in candidate.principal_committees
        ],
    }


async def load_candidates() -> int:
    if not STAGING_PATH.exists():
        raise FileNotFoundError(
            f"no candidate staging data at {STAGING_PATH} — run the fec_candidates pipeline first"
        )

    try:
        staged = FecCandidateSnapshotRaw.model_validate_json(
            STAGING_PATH.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise ValueError("candidate staging snapshot is invalid") from exc

    if staged.source != "fec_candidates" or not staged.complete:
        raise ValueError("refusing to load a candidate snapshot not marked complete")
    if staged.candidate_count != len(staged.candidates) or not staged.candidates:
        raise ValueError("candidate staging count does not match the complete snapshot")
    candidate_ids = [candidate.candidate_id for candidate in staged.candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate staging snapshot contains duplicate FEC IDs")

    rows = [_candidate_row(staged.finance_cycle, candidate) for candidate in staged.candidates]
    coverage = {
        "finance_cycle": staged.finance_cycle,
        "complete": True,
        "candidate_count": len(rows),
        "expected_count": staged.expected_count,
        "page_count": staged.page_count,
        "snapshot_revision": staged.snapshot_revision,
        "fetched_at": staged.fetched_at,
    }

    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                delete(ElectionCandidate).where(
                    ElectionCandidate.finance_cycle == staged.finance_cycle
                )
            )
            for start in range(0, len(rows), _CHUNK):
                await session.execute(
                    pg_insert(ElectionCandidate).values(rows[start : start + _CHUNK])
                )
            stmt = pg_insert(ElectionCatalogCoverage).values(coverage)
            stmt = stmt.on_conflict_do_update(
                index_elements=[ElectionCatalogCoverage.finance_cycle],
                set_={
                    key: getattr(stmt.excluded, key)
                    for key in coverage
                    if key != "finance_cycle"
                },
            )
            await session.execute(stmt)

    logger.info(
        "elections: atomically replaced %d candidates for finance cycle %d",
        len(rows),
        staged.finance_cycle,
    )
    return len(rows)


if __name__ == "__main__":
    asyncio.run(load_candidates())
