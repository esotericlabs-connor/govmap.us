import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.pipelines import zip_crosswalk


class _Response:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode()
        self.headers: dict[str, str] = {}
        self.raw = None
        self.closed = False

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, chunk_size: int = 1) -> Iterator[bytes]:
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def close(self) -> None:
        self.closed = True


def _response(rows: list[dict[str, str]]) -> _Response:
    return _Response({"data": {"results": rows}})


def _row(zip_code: str) -> dict[str, str]:
    return {"zip": zip_code, "geoid": "0603"}


def test_hud_stages_only_after_completion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(zip_crosswalk.settings, "hud_api_token", "test-placeholder")
    monkeypatch.setattr(zip_crosswalk, "_MAX_PAGES", 3)
    monkeypatch.setattr(zip_crosswalk, "STAGING_DIR", tmp_path)
    path = tmp_path / "zip_districts_raw.json"
    monkeypatch.setattr(zip_crosswalk, "STAGING_PATH", path)
    responses = [_response([_row("90001")]), _response([_row("90002")]), _response([])]
    get = Mock(side_effect=responses)
    monkeypatch.setattr(zip_crosswalk.requests, "get", get)
    assert zip_crosswalk.run() == 2
    assert [row["zip"] for row in json.loads(path.read_text())] == ["90001", "90002"]
    assert get.call_count == 3
    assert get.call_args.kwargs["stream"] is True
    assert all(response.closed for response in responses)


def test_hud_page_limit_preserves_previous_staging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(zip_crosswalk.settings, "hud_api_token", "test-placeholder")
    monkeypatch.setattr(zip_crosswalk, "_MAX_PAGES", 2)
    monkeypatch.setattr(zip_crosswalk, "STAGING_DIR", tmp_path)
    path = tmp_path / "zip_districts_raw.json"
    previous = '[{"zip":"98001","state":"WA","district":9}]'
    path.write_text(previous)
    monkeypatch.setattr(zip_crosswalk, "STAGING_PATH", path)
    get = Mock(side_effect=[
        _response([_row("90001")]),
        _response([_row("90002")]),
    ])
    monkeypatch.setattr(zip_crosswalk.requests, "get", get)
    with pytest.raises(RuntimeError, match="refusing to stage an incomplete"):
        zip_crosswalk.run()
    assert path.read_text() == previous
    assert get.call_count == 2


def test_hud_existing_single_page_repeat_behavior_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(zip_crosswalk.settings, "hud_api_token", "test-placeholder")
    monkeypatch.setattr(zip_crosswalk, "_MAX_PAGES", 2)
    rows = [_row("90001")]
    monkeypatch.setattr(
        zip_crosswalk.requests, "get", Mock(side_effect=[_response(rows), _response(rows)])
    )
    assert zip_crosswalk._fetch() == rows
