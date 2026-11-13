"""Layer 1 pipeline: complete, bounded OpenFEC candidate snapshots by cycle."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.config import settings
from app.pipelines.batch import BatchResult
from app.pipelines.fec_finance import _fec_get
from app.pipelines.staging import write_json_atomic
from app.schemas.election import FecCandidatePageRaw, FecCandidateSnapshotRaw

logger = logging.getLogger(__name__)

SOURCE_NAME = "fec_candidates"
STAGING_PATH = Path(__file__).resolve().parents[2] / "data" / "staging" / "fec_candidates_raw.json"

_PAGE_SIZE = 100
_MAX_PAGES = 100
_PAGE_PAUSE_SECONDS = 0.1


class CandidateSnapshotIncompleteError(RuntimeError):
    """The source response cannot prove a complete candidate-cycle snapshot."""


def _expected_count(page: FecCandidatePageRaw) -> int | None:
    count = page.pagination.get("count")
    if count is None:
        return None
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise CandidateSnapshotIncompleteError("OpenFEC candidate pagination count is malformed")
    return count


def run() -> BatchResult:
    """Fetch one complete cycle snapshot; never stage an incomplete page walk."""
    if not settings.fec_api_key:
        raise RuntimeError("FEC_API_KEY is not set — required for the candidate catalog")

    finance_cycle = settings.fec_cycle
    candidates = []
    seen_ids: set[str] = set()
    expected_count: int | None = None
    expected_count_changed = False
    page_count = 0
    complete = False

    for page_number in range(1, _MAX_PAGES + 2):
        if page_number > 1:
            time.sleep(_PAGE_PAUSE_SECONDS)
        payload = _fec_get(
            "candidates",
            cycle=finance_cycle,
            page=page_number,
            per_page=_PAGE_SIZE,
        )
        try:
            page = FecCandidatePageRaw.model_validate(payload)
        except ValidationError as exc:
            raise CandidateSnapshotIncompleteError(
                f"OpenFEC candidate page {page_number} has an invalid shape"
            ) from exc

        page_count = page_number
        page_expected = _expected_count(page)
        if page_number == 1:
            expected_count = page_expected
        elif page_expected is not None:
            if expected_count is None:
                expected_count = page_expected
            elif expected_count != page_expected:
                expected_count_changed = True

        if page_number > _MAX_PAGES:
            if page.results:
                raise CandidateSnapshotIncompleteError(
                    f"OpenFEC candidate catalog exceeded {_MAX_PAGES} pages"
                )
            complete = True
            break
        if len(page.results) > _PAGE_SIZE:
            raise CandidateSnapshotIncompleteError(
                f"OpenFEC returned more than {_PAGE_SIZE} candidates on one page"
            )

        for candidate in page.results:
            if candidate.candidate_id in seen_ids:
                raise CandidateSnapshotIncompleteError(
                    "OpenFEC candidate IDs repeated during pagination; refusing an unstable snapshot"
                )
            seen_ids.add(candidate.candidate_id)
            candidates.append(candidate)

        if not page.results or len(page.results) < _PAGE_SIZE:
            complete = True
            break

    if not complete:
        raise CandidateSnapshotIncompleteError(
            "OpenFEC candidate page walk did not reach a complete boundary"
        )
    if not candidates:
        raise CandidateSnapshotIncompleteError(
            f"OpenFEC returned no candidates for finance cycle {finance_cycle}"
        )
    if expected_count_changed:
        logger.warning(
            "OpenFEC candidate count changed during pagination; using the terminal page "
            "boundary as completion evidence"
        )

    candidate_rows = [
        candidate.model_dump(mode="json")
        for candidate in sorted(candidates, key=lambda row: row.candidate_id)
    ]
    revision = hashlib.sha256(
        json.dumps(candidate_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    snapshot = FecCandidateSnapshotRaw(
        source=SOURCE_NAME,
        finance_cycle=finance_cycle,
        complete=True,
        candidate_count=len(candidate_rows),
        expected_count=expected_count,
        page_count=page_count,
        snapshot_revision=revision,
        fetched_at=datetime.now(UTC),
        candidates=candidate_rows,
    )
    write_json_atomic(STAGING_PATH, snapshot.model_dump(mode="json"), indent=2)

    logger.info(
        "%s: staged %d candidates for finance cycle %d across %d page(s)",
        SOURCE_NAME,
        len(candidate_rows),
        finance_cycle,
        page_count,
    )
    return BatchResult(total=len(candidate_rows), succeeded=len(candidate_rows), failed=0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
