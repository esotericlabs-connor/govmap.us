import json
from pathlib import Path

import pytest

from app.normalize.guards import check_replacement
from app.normalize.votes import replaceable_vote_ids
from app.pipelines.staging import write_json_atomic


def test_atomic_write_round_trips_and_leaves_no_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "snapshot.json"
    write_json_atomic(target, [{"id": 1}], indent=2)
    write_json_atomic(target, [{"id": 2}])
    assert json.loads(target.read_text(encoding="utf-8")) == [{"id": 2}]
    assert [p.name for p in target.parent.iterdir()] == ["snapshot.json"]


def test_failed_write_keeps_the_previous_snapshot(tmp_path: Path) -> None:
    target = tmp_path / "snapshot.json"
    write_json_atomic(target, [{"id": 1}])
    with pytest.raises(TypeError):
        write_json_atomic(target, [{"id": 2}, object()])
    assert json.loads(target.read_text(encoding="utf-8")) == [{"id": 1}]
    assert [p.name for p in tmp_path.iterdir()] == ["snapshot.json"]


@pytest.mark.parametrize(
    ("new_rows", "current_rows", "min_ratio"),
    [(0, 0, 0.0), (0, 500, 0.0), (249, 500, 0.5)],
)
def test_replacement_guard_refuses_empty_or_collapsed_snapshots(
    new_rows: int, current_rows: int, min_ratio: float
) -> None:
    with pytest.raises(ValueError, match="refusing"):
        check_replacement("t", new_rows, current_rows, min_ratio=min_ratio)


@pytest.mark.parametrize(
    ("new_rows", "current_rows", "min_ratio"),
    [(1, 0, 0.5), (1, 500, 0.0), (250, 500, 0.5), (900, 500, 0.5)],
)
def test_replacement_guard_allows_plausible_snapshots(
    new_rows: int, current_rows: int, min_ratio: float
) -> None:
    check_replacement("t", new_rows, current_rows, min_ratio=min_ratio)


def test_votes_without_resolved_positions_keep_their_stored_positions() -> None:
    votes = [{"vote_id": v} for v in ("v1", "v2", "v1", "v3")]
    positions = [{"vote_id": "v3"}, {"vote_id": "v1"}, {"vote_id": "v1"}]
    assert replaceable_vote_ids(votes, positions) == ["v1", "v3"]
    assert replaceable_vote_ids(votes, []) == []
