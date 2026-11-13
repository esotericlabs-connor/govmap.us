import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import settings
from app.normalize import elections as election_normalizer
from app.pipelines import fec_candidates


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
