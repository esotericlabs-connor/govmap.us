import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.config import settings
from app.normalize import elections as election_normalizer
from app.normalize.dates import normalize_date
from app.pipelines import fec_candidates
from app.schemas.election import FecCandidateRaw


def _candidate(candidate_id: str = "H0CA00001") -> dict:
    return {
        "candidate_id": candidate_id,
        "name": "Example Candidate",
        "office": "H",
        "office_full": "House",
        "state": "CA",
        "district": "01",
        "party": "DEM",
        "party_full": "Democratic Party",
        "candidate_status": "C",
        "incumbent_challenge": "C",
        "first_file_date": "2025-01-01",
        "last_file_date": "2025-02-01",
        "cycles": [2026],
        "election_years": [2026],
        "principal_committees": [{"committee_id": "C00000001"}],
    }


@pytest.mark.parametrize("with_dates", [True, False])
def test_candidate_dates_use_shared_normalizer(
    monkeypatch: pytest.MonkeyPatch, with_dates: bool
) -> None:
    raw = _candidate()
    if not with_dates:
        raw["first_file_date"] = None
        raw["last_file_date"] = None
    candidate = FecCandidateRaw.model_validate(raw)
    seen: list[object] = []

    def normalize_spy(value: object) -> date | None:
        seen.append(value)
        return normalize_date(value)

    monkeypatch.setattr(election_normalizer, "normalize_date", normalize_spy)
    row = election_normalizer._candidate_row(2026, candidate)

    assert seen == [candidate.first_file_date, candidate.last_file_date]
    assert row["first_file_date"] == candidate.first_file_date
    assert row["last_file_date"] == candidate.last_file_date


def test_candidate_pipeline_stages_only_a_complete_page_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    monkeypatch.setattr(settings, "fec_cycle", 2026)
    monkeypatch.setattr(fec_candidates, "STAGING_PATH", tmp_path / "candidates.json")
    monkeypatch.setattr(fec_candidates, "_PAGE_SIZE", 1)
    monkeypatch.setattr(fec_candidates, "_PAGE_PAUSE_SECONDS", 0)
    requested: list[dict] = []

    def fake_get(_path: str, **params: object) -> dict:
        requested.append(params)
        if params["page"] == 1:
            return {"results": [_candidate()], "pagination": {"count": 1}}
        return {"results": [], "pagination": {"count": 1}}

    monkeypatch.setattr(fec_candidates, "_fec_get", fake_get)

    result = fec_candidates.run()
    staged = json.loads((tmp_path / "candidates.json").read_text(encoding="utf-8"))

    assert result.succeeded == 1
    assert staged["complete"] is True
    assert staged["candidate_count"] == 1
    assert staged["expected_count"] == 1
    assert staged["page_count"] == 2
    assert staged["candidates"][0]["candidate_id"] == "H0CA00001"
    assert requested[0]["cycle"] == 2026
    assert requested[0]["per_page"] == 1
    assert requested[0]["sort"] == "candidate_id"


def test_exact_candidate_count_mismatch_preserves_previous_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    staging = tmp_path / "candidates.json"
    staging.write_text('{"previous":"snapshot"}', encoding="utf-8")
    monkeypatch.setattr(fec_candidates, "STAGING_PATH", staging)
    monkeypatch.setattr(
        fec_candidates,
        "_fec_get",
        lambda *_args, **_kwargs: {
            "results": [_candidate()],
            "pagination": {"count": 2, "is_count_exact": True},
        },
    )

    with pytest.raises(fec_candidates.CandidateSnapshotIncompleteError, match="exact count"):
        fec_candidates.run()
    assert json.loads(staging.read_text(encoding="utf-8")) == {"previous": "snapshot"}


def test_matching_exact_candidate_count_can_be_staged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    staging = tmp_path / "candidates.json"
    monkeypatch.setattr(fec_candidates, "STAGING_PATH", staging)
    monkeypatch.setattr(
        fec_candidates,
        "_fec_get",
        lambda *_args, **_kwargs: {
            "results": [_candidate()],
            "pagination": {"count": 1, "is_count_exact": True},
        },
    )

    result = fec_candidates.run()
    assert result.succeeded == 1
    assert json.loads(staging.read_text(encoding="utf-8"))["expected_count"] == 1


def test_changed_exact_candidate_count_preserves_previous_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    monkeypatch.setattr(fec_candidates, "_PAGE_SIZE", 1)
    monkeypatch.setattr(fec_candidates, "_PAGE_PAUSE_SECONDS", 0)
    staging = tmp_path / "candidates.json"
    staging.write_text('{"previous":"snapshot"}', encoding="utf-8")
    monkeypatch.setattr(fec_candidates, "STAGING_PATH", staging)

    def fake_get(_path: str, **params: object) -> dict:
        if params["page"] == 1:
            return {"results": [_candidate()], "pagination": {"count": 2, "is_count_exact": True}}
        return {
            "results": [_candidate("H0CA00002")],
            "pagination": {"count": 3, "is_count_exact": True},
        }

    monkeypatch.setattr(fec_candidates, "_fec_get", fake_get)
    with pytest.raises(fec_candidates.CandidateSnapshotIncompleteError, match="count changed"):
        fec_candidates.run()
    assert json.loads(staging.read_text(encoding="utf-8")) == {"previous": "snapshot"}


def test_candidate_page_cap_does_not_replace_existing_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    monkeypatch.setattr(fec_candidates, "STAGING_PATH", tmp_path / "candidates.json")
    monkeypatch.setattr(fec_candidates, "_PAGE_SIZE", 1)
    monkeypatch.setattr(fec_candidates, "_MAX_PAGES", 1)
    monkeypatch.setattr(fec_candidates, "_PAGE_PAUSE_SECONDS", 0)
    staging = tmp_path / "candidates.json"
    staging.write_text('{"previous":"snapshot"}', encoding="utf-8")
    monkeypatch.setattr(
        fec_candidates,
        "_fec_get",
        lambda *_args, **_kwargs: {
            "results": [_candidate()],
            "pagination": {"count": 2},
        },
    )

    with pytest.raises(fec_candidates.CandidateSnapshotIncompleteError, match="exceeded 1 pages"):
        fec_candidates.run()

    assert json.loads(staging.read_text(encoding="utf-8")) == {"previous": "snapshot"}


def test_invalid_candidate_response_does_not_replace_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "test-key")
    monkeypatch.setattr(fec_candidates, "STAGING_PATH", tmp_path / "candidates.json")
    staging = tmp_path / "candidates.json"
    staging.write_text('{"previous":"snapshot"}', encoding="utf-8")
    monkeypatch.setattr(
        fec_candidates,
        "_fec_get",
        lambda *_args, **_kwargs: {"results": [{"name": "Missing source ID"}]},
    )

    with pytest.raises(fec_candidates.CandidateSnapshotIncompleteError, match="invalid shape"):
        fec_candidates.run()

    assert json.loads(staging.read_text(encoding="utf-8")) == {"previous": "snapshot"}


def test_normalizer_refuses_incomplete_candidate_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "candidates.json"
    staging.write_text(
        json.dumps(
            {
                "source": "fec_candidates",
                "finance_cycle": 2026,
                "complete": False,
                "candidate_count": 1,
                "expected_count": 1,
                "page_count": 1,
                "snapshot_revision": "a" * 64,
                "fetched_at": datetime.now(UTC).isoformat(),
                "candidates": [_candidate()],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(election_normalizer, "STAGING_PATH", staging)

    with pytest.raises(ValueError, match="not marked complete"):
        asyncio.run(election_normalizer.load_candidates())
