"""Regression tests for the roll-call vote pipelines.

Pins three live failures seen in production:
- the House Clerk soft-404 (HTTP 200 + `<xml>Error sanitizing ...</xml>` for a
  missing 3-digit roll) that made the max-roll search converge on 999 and the
  run parse nothing;
- the Senate menu's observed HTTP 403, which must surface as a
  failure (never "no votes") so refresh_votes falls back to Voteview;
- the Voteview fallback itself: CSV shape validation, cast-code mapping,
  Bioguide binding, source attribution, and download reuse.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
import requests
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert

from app.config import settings
from app.normalize import votes as vote_normalizer
from app.pipelines import (
    house_clerk_votes,
    refresh,
    senate_lis_votes,
    voteview_senate_votes,
)

# Verbatim body the Clerk returns (HTTP 200) for a roll that doesn't exist.
SOFT_404 = b'<xml>Error sanitizing file "roll999.xml". Please try again.</xml>'


class _Resp:
    def __init__(self, status_code: int, content: bytes) -> None:
        self.status_code = status_code
        self.content = content
        self.headers: dict[str, str] = {}
        self.raw = None

    def iter_content(self, chunk_size: int = 1) -> Iterator[bytes]:
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]

    def close(self) -> None:
        pass


@pytest.fixture
def session_119_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "congress_number", 119)
    monkeypatch.setattr(settings, "congress_session", 2)


# --- House Clerk ------------------------------------------------------------


def _roll_xml(n: int) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rollcall-vote>
  <vote-metadata>
    <rollcall-num>{n}</rollcall-num>
    <legis-num>H R {n}</legis-num>
    <vote-question>On Passage</vote-question>
    <vote-result>Passed</vote-result>
    <action-date>6-Jan-2026</action-date>
    <vote-totals><totals-by-vote>
      <yea-total>1</yea-total><nay-total>0</nay-total>
      <present-total>0</present-total><not-voting-total>0</not-voting-total>
    </totals-by-vote></vote-totals>
  </vote-metadata>
  <vote-data>
    <recorded-vote><legislator name-id="A000001">Adams</legislator><vote>Yea</vote></recorded-vote>
  </vote-data>
</rollcall-vote>""".encode()


def _clerk(top: int, roll_one: _Resp | None = None) -> Callable[..., _Resp]:
    """Mimics clerk.house.gov: rolls 1..top exist; any other 3-digit roll is the
    HTTP-200 soft-404; 4-digit rolls are a real 404."""

    def get(url: str, **_: object) -> _Resp:
        n = int(url.rsplit("/roll", 1)[1].removesuffix(".xml"))
        if n == 1 and roll_one is not None:
            return roll_one
        if 1 <= n <= top:
            return _Resp(200, _roll_xml(n))
        if n < 1000:
            return _Resp(200, SOFT_404)
        return _Resp(404, b"Not Found")

    return get


@pytest.fixture
def house_staging(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "house_votes_raw.json"
    monkeypatch.setattr(house_clerk_votes, "STAGING", path)
    return path


@pytest.mark.parametrize(
    ("response", "exists"),
    [
        (_Resp(200, _roll_xml(5)), True),
        (_Resp(200, SOFT_404), False),
        (_Resp(404, b"Not Found"), False),
    ],
)
def test_exists_requires_a_roll_document_not_just_http_200(
    monkeypatch: pytest.MonkeyPatch, response: _Resp, exists: bool
) -> None:
    monkeypatch.setattr(house_clerk_votes._session, "get", Mock(return_value=response))
    assert house_clerk_votes._exists(2026, 5) is exists


def test_max_roll_is_not_fooled_by_soft_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(house_clerk_votes._session, "get", _clerk(top=137))
    assert house_clerk_votes._max_roll(2026) == 137


def test_run_stages_newest_real_rolls(
    session_119_2: None, house_staging: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "votes_limit", 5)
    monkeypatch.setattr(house_clerk_votes._session, "get", _clerk(top=137))
    assert house_clerk_votes.run() == 5
    staged = json.loads(house_staging.read_text())
    assert [v["roll_number"] for v in staged] == [137, 136, 135, 134, 133]
    assert staged[0]["vote_id"] == "h119-2-137"
    assert staged[0]["positions"] == [{"bioguide_id": "A000001", "position": "Yea"}]


def test_run_treats_soft_404_roll_one_as_no_votes_yet(
    session_119_2: None, house_staging: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(house_clerk_votes._session, "get", _clerk(top=0))
    assert house_clerk_votes.run() == 0
    assert json.loads(house_staging.read_text()) == []


@pytest.mark.parametrize(
    "roll_one",
    [_Resp(403, b"Forbidden"), _Resp(200, b"<html><body>challenge</body></html>")],
)
def test_run_surfaces_a_blocked_clerk(
    session_119_2: None, house_staging: Path, monkeypatch: pytest.MonkeyPatch, roll_one: _Resp
) -> None:
    monkeypatch.setattr(house_clerk_votes._session, "get", _clerk(top=137, roll_one=roll_one))
    with pytest.raises(RuntimeError, match="unexpected response|HTTP 403"):
        house_clerk_votes.run()
    assert not house_staging.exists()


@pytest.mark.parametrize(
    "response",
    [_Resp(403, b"Forbidden"), _Resp(503, b"Unavailable"), _Resp(200, b"<html>challenge</html>")],
)
def test_probe_failure_is_not_a_missing_roll(
    monkeypatch: pytest.MonkeyPatch, response: _Resp
) -> None:
    monkeypatch.setattr(house_clerk_votes._session, "get", Mock(return_value=response))
    with pytest.raises(RuntimeError):
        house_clerk_votes._exists(2026, 128)


def test_probe_timeout_does_not_truncate_the_roll_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        house_clerk_votes._session, "get", Mock(side_effect=requests.ReadTimeout("timeout"))
    )
    with pytest.raises(requests.ReadTimeout):
        house_clerk_votes._max_roll(2026)


def test_house_failed_detail_preserves_previous_staging(
    session_119_2: None, house_staging: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    house_staging.write_text("previous snapshot")
    monkeypatch.setattr(house_clerk_votes, "_max_roll", lambda _: 2)
    monkeypatch.setattr(settings, "votes_limit", 2)
    monkeypatch.setattr(
        house_clerk_votes._session, "get",
        Mock(side_effect=[_Resp(200, _roll_xml(2)), _Resp(503, b"Unavailable")]),
    )
    with pytest.raises(RuntimeError, match="HTTP 503"):
        house_clerk_votes.run()
    assert house_staging.read_text() == "previous snapshot"


# --- Senate LIS -------------------------------------------------------------


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_Resp(403, b"<html><body>Access Denied</body></html>"), "HTTP 403"),
        (_Resp(200, b"<html><body>Access Denied</body></html>"), "unexpected root"),
        (_Resp(200, b"<<not xml"), "not parseable"),
    ],
)
def test_senate_menu_failure_raises_instead_of_reading_as_no_votes(
    monkeypatch: pytest.MonkeyPatch, response: _Resp, message: str
) -> None:
    monkeypatch.setattr(senate_lis_votes._session, "get", Mock(return_value=response))
    with pytest.raises(RuntimeError, match=message):
        senate_lis_votes._menu_numbers(119, 2)


def test_senate_menu_lists_vote_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    menu = (
        b"<vote_summary><votes>"
        b"<vote><vote_number>00002</vote_number></vote>"
        b"<vote><vote_number>00001</vote_number></vote>"
        b"</votes></vote_summary>"
    )
    monkeypatch.setattr(senate_lis_votes._session, "get", Mock(return_value=_Resp(200, menu)))
    assert senate_lis_votes._menu_numbers(119, 2) == [2, 1]


def test_senate_detail_failure_preserves_previous_staging(
    session_119_2: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "senate.json"
    path.write_text("previous snapshot")
    monkeypatch.setattr(senate_lis_votes, "STAGING", path)
    monkeypatch.setattr(senate_lis_votes, "_menu_numbers", lambda *_: [1])
    monkeypatch.setattr(senate_lis_votes._session, "get", Mock(return_value=_Resp(403, b"blocked")))
    with pytest.raises(RuntimeError, match="HTTP 403"):
        senate_lis_votes.run()
    assert path.read_text() == "previous snapshot"


# --- Voteview fallback --------------------------------------------------------

_ROLLCALLS = (
    "congress,chamber,rollnumber,date,session,clerk_rollnumber,majority_requirement,"
    "yea_count,nay_count,nominate_mid_1,nominate_mid_2,nominate_spread_1,"
    "nominate_spread_2,nominate_log_likelihood,bill_number,vote_result,vote_desc,"
    "vote_question,dtl_desc\n"
    '119,Senate,658,2025-12-18,1,659,1/2,2,0,,,,,,PN100,Nomination Confirmed,"X, to be Y",On the Nomination,\n'
    '119,Senate,700,2026-01-07,2,1,1/2,2,1,,,,,,SJRES198,Motion to Proceed Rejected,'
    '"Medicare &#38; Medicaid rule",On the Motion to Proceed &#38; Such,\n'
    '119,Senate,701,2026-01-08,2,2,3/5,1,1,,,,,,HR5334,Cloture Motion Agreed to,"A bill",On the Cloture Motion,\n'
)
_MEMBERS = (
    "congress,chamber,icpsr,state_icpsr,district_code,state_abbrev,party_code,"
    "occupancy,last_means,bioname,bioguide_id,born,died\n"
    '119,President,99912,99,0,USA,200,0,0,"TRUMP, Donald John",,1946.0,\n'
    '119,Senate,1,41,0,AL,200,,,"A, A",A000001,1950.0,\n'
    '119,Senate,2,41,0,AL,100,,,"B, B",B000002,1950.0,\n'
    '119,Senate,3,81,0,AK,200,,,"C, C",C000003,1950.0,\n'
    '119,Senate,4,81,0,AK,200,,,"D, D",D000004,1950.0,\n'
)
_VOTES = (
    "congress,chamber,rollnumber,icpsr,cast_code,prob\n"
    "119,Senate,700,1,1,100.0\n"
    "119,Senate,700,2,6,100.0\n"
    "119,Senate,700,3,1,100.0\n"
    "119,Senate,700,4,9,100.0\n"
    "119,Senate,701,1,1,100.0\n"
    "119,Senate,701,2,2,100.0\n"
    "119,Senate,701,3,6,100.0\n"
    "119,Senate,701,4,0,\n"
    "119,President,701,99912,1,\n"
    "119,Senate,658,1,1,100.0\n"
)


def _voteview(
    rollcalls: str = _ROLLCALLS, members: str = _MEMBERS, votes: str = _VOTES, status: int = 200
) -> Mock:
    files = {"rollcalls": rollcalls, "members": members, "votes": votes}

    def get(url: str, **_: object) -> _Resp:
        kind = url.rsplit("/", 2)[-2]
        assert url == f"https://voteview.com/static/data/out/{kind}/S119_{kind}.csv"
        return _Resp(status, files[kind].encode())

    return Mock(side_effect=get)


@pytest.fixture
def voteview_staging(
    session_119_2: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    path = tmp_path / "senate_votes_raw.json"
    monkeypatch.setattr(voteview_senate_votes, "STAGING", path)
    monkeypatch.setattr(settings, "votes_limit", 2)
    monkeypatch.setattr(settings, "voteview_min_refetch_hours", 6)
    return path


@pytest.mark.parametrize(
    ("bill_number", "bill_id"),
    [
        ("S5", "s5-119"),
        ("HR6644", "hr6644-119"),
        ("SJRES118", "sjres118-119"),
        ("HCONRES86", "hconres86-119"),
        ("SRES616", "sres616-119"),
        ("HRES07", "hres7-119"),
        ("PN1113", None),
        ("", None),
        (None, None),
    ],
)
def test_bill_id_from_voteview(bill_number: str | None, bill_id: str | None) -> None:
    assert voteview_senate_votes.bill_id_from_voteview(bill_number, 119) == bill_id


def test_voteview_run_stages_lis_compatible_votes(
    voteview_staging: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voteview_senate_votes._session, "get", _voteview())
    # Session 1 is excluded, and no selected member positions are silently lost.
    assert voteview_senate_votes.run() == 2
    staged = json.loads(voteview_staging.read_text())
    assert [v["vote_id"] for v in staged] == ["s119-2-2", "s119-2-1"]

    paired = staged[0]
    assert paired["positions"] == [
        {"bioguide_id": "A000001", "position": "Yea"},
        {"bioguide_id": "B000002", "position": "Not Voting"},
        {"bioguide_id": "C000003", "position": "Nay"},
    ]
    assert paired["totals"] == {"yea": 1, "nay": 1, "present": 0, "absent": 1}

    first = staged[1]
    assert first == {
        "vote_id": "s119-2-1",
        "chamber": "senate",
        "congress": 119,
        "session": 2,
        "roll_number": 1,
        "date": "2026-01-07",
        "question": "On the Motion to Proceed & Such",
        "result": "Motion to Proceed Rejected",
        "bill_id": "sjres198-119",
        "totals": {"yea": 2, "nay": 1, "present": 0, "absent": 1},
        "source_url": "https://voteview.com/static/data/out/votes/S119_votes.csv",
        "provenance": "voteview",
        "positions": [
            {"bioguide_id": "A000001", "position": "Yea"},
            {"bioguide_id": "B000002", "position": "Nay"},
            {"bioguide_id": "C000003", "position": "Yea"},
            {"bioguide_id": "D000004", "position": "Not Voting"},
        ],
    }


def test_voteview_run_fails_when_no_selected_vote_has_positions(
    voteview_staging: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "votes_limit", 1)
    votes = "\n".join(line for line in _VOTES.splitlines() if ",Senate,701," not in line) + "\n"
    monkeypatch.setattr(voteview_senate_votes._session, "get", _voteview(votes=votes))
    with pytest.raises(ValueError, match="no member positions"):
        voteview_senate_votes.run()
    assert not voteview_staging.exists()


@pytest.mark.parametrize(
    ("fetch", "error", "message"),
    [
        (_voteview(rollcalls=_ROLLCALLS.replace("clerk_rollnumber", "clerk_num")), ValueError, "clerk_rollnumber"),
        (_voteview(status=503), RuntimeError, "HTTP 503"),
    ],
)
def test_voteview_shape_or_http_failures_raise(
    voteview_staging: Path,
    monkeypatch: pytest.MonkeyPatch,
    fetch: Mock,
    error: type[Exception],
    message: str,
) -> None:
    monkeypatch.setattr(voteview_senate_votes._session, "get", fetch)
    with pytest.raises(error, match=message):
        voteview_senate_votes.run()
    assert not voteview_staging.exists()


def test_voteview_reuses_a_fresh_staged_pull(
    voteview_staging: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voteview_senate_votes._session, "get", _voteview())
    assert voteview_senate_votes.run() == 2
    get = Mock(side_effect=AssertionError("must not download"))
    monkeypatch.setattr(voteview_senate_votes._session, "get", get)
    assert voteview_senate_votes.run() == 2
    get.assert_not_called()


@pytest.mark.parametrize(
    ("staged", "age_hours"),
    [
        ([{"vote_id": "s119-2-1", "congress": 119, "session": 2, "provenance": "voteview"}], 7),
        ([{"vote_id": "s119-2-1", "congress": 119, "session": 2}], 0),
        ([{"vote_id": "s119-1-1", "congress": 119, "session": 1, "provenance": "voteview"}], 0),
    ],
    ids=["stale", "official-lis-staging", "other-session"],
)
def test_voteview_refetches_when_staging_is_not_reusable(
    voteview_staging: Path, monkeypatch: pytest.MonkeyPatch, staged: list[dict], age_hours: int
) -> None:
    voteview_staging.write_text(json.dumps(staged))
    old = time.time() - age_hours * 3600
    os.utime(voteview_staging, (old, old))
    fetch = _voteview()
    monkeypatch.setattr(voteview_senate_votes._session, "get", fetch)
    assert voteview_senate_votes.run() == 2
    assert fetch.call_count == 3


def test_voteview_rejects_inconsistent_cached_totals(
    voteview_staging: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = _voteview()
    monkeypatch.setattr(voteview_senate_votes._session, "get", fetch)
    assert voteview_senate_votes.run() == 2
    data = json.loads(voteview_staging.read_text())
    data[0]["totals"]["yea"] = 99
    voteview_staging.write_text(json.dumps(data))
    fetch.reset_mock()
    assert voteview_senate_votes.run() == 2
    assert fetch.call_count == 3
    assert json.loads(voteview_staging.read_text())[0]["totals"]["yea"] == 1


@pytest.mark.parametrize("extra_byte", [0, 1])
def test_voteview_csv_byte_limit(monkeypatch: pytest.MonkeyPatch, extra_byte: int) -> None:
    monkeypatch.setattr(voteview_senate_votes._session, "get", _voteview())
    monkeypatch.setattr(voteview_senate_votes, "_MAX_CSV_BYTES", len(_VOTES.encode()) - extra_byte)
    if extra_byte:
        with pytest.raises(RuntimeError, match="larger than"):
            voteview_senate_votes._fetch_csv("votes", 119, voteview_senate_votes._CAST_COLUMNS)
    else:
        assert voteview_senate_votes._fetch_csv("votes", 119, voteview_senate_votes._CAST_COLUMNS)


# --- refresh_votes orchestration ---------------------------------------------

_FALLBACK_NOTE = (
    "senate via voteview_senate_votes fallback (senate.gov LIS unavailable; "
    "official coverage/freshness unverified)"
)


def _patch_refresh(
    monkeypatch: pytest.MonkeyPatch, house: Mock, lis: Mock, fallback: Mock
) -> AsyncMock:
    monkeypatch.setattr(house_clerk_votes, "run", house)
    monkeypatch.setattr(senate_lis_votes, "run", lis)
    monkeypatch.setattr(voteview_senate_votes, "run", fallback)
    monkeypatch.setattr(refresh, "normalize_votes", AsyncMock(return_value=12))
    record = AsyncMock()
    monkeypatch.setattr(refresh, "record_run", record)
    return record


def _blocked() -> Mock:
    return Mock(side_effect=RuntimeError("senate vote menu returned HTTP 403 (119_2)"))


@pytest.mark.parametrize(
    ("house", "lis", "fallback", "status", "detail", "fallback_calls"),
    [
        (Mock(return_value=5), Mock(return_value=5), Mock(return_value=7), "ok", None, 0),
        (Mock(return_value=5), _blocked(), Mock(return_value=7), "partial", _FALLBACK_NOTE, 1),
        (
            Mock(return_value=5),
            _blocked(),
            Mock(side_effect=RuntimeError("voteview votes returned HTTP 503")),
            "partial",
            "chamber(s) failed: senate",
            1,
        ),
        (
            Mock(side_effect=ValueError("no house votes parsed")),
            _blocked(),
            Mock(return_value=7),
            "partial",
            f"chamber(s) failed: house; {_FALLBACK_NOTE}",
            1,
        ),
    ],
    ids=["official", "senate-fallback", "senate-down", "house-down-senate-fallback"],
)
def test_refresh_votes_senate_fallback(
    monkeypatch: pytest.MonkeyPatch,
    house: Mock,
    lis: Mock,
    fallback: Mock,
    status: str,
    detail: str | None,
    fallback_calls: int,
) -> None:
    record = _patch_refresh(monkeypatch, house, lis, fallback)
    if status == "partial":
        with pytest.raises(refresh.VoteRefreshIncompleteError):
            asyncio.run(refresh.refresh_votes())
    else:
        asyncio.run(refresh.refresh_votes())
    assert fallback.call_count == fallback_calls
    record.assert_awaited_once_with("votes", 12, status, detail)
    refresh.normalize_votes.assert_awaited_once_with(
        include_house=not (detail or "").startswith("chamber(s) failed: house"),
        include_senate=detail != "chamber(s) failed: senate",
    )


def test_refresh_votes_raises_when_both_chambers_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _patch_refresh(
        monkeypatch,
        Mock(side_effect=ValueError("no house votes parsed")),
        _blocked(),
        Mock(side_effect=RuntimeError("voteview down")),
    )
    with pytest.raises(RuntimeError, match="both House and Senate"):
        asyncio.run(refresh.refresh_votes())
    record.assert_awaited_once_with("votes", 0, "error", "both House and Senate vote pulls failed")


@pytest.mark.parametrize(
    "fetch",
    [
        _voteview(members=_MEMBERS.replace("D000004", "invalid")),
        _voteview(votes=_VOTES + "119,Senate,701,1,1,\n"),
        _voteview(votes=_VOTES.replace("700,1,1,", "700,1,99,")),
        _voteview(rollcalls=_ROLLCALLS.replace("2,1,1/2,2,1,", "2,1,1/2,99,1,")),
        _voteview(votes=_VOTES.replace("119,Senate,700", "118,Senate,700")),
        _voteview(votes=_VOTES + "119,Senate,701\n"),
        _voteview(votes="congress,chamber,rollnumber,icpsr,cast_code,prob\n"),
    ],
    ids=["unmapped-member", "duplicate-position", "unknown-code", "tally-mismatch",
         "wrong-congress", "truncated-row", "empty-file"],
)
def test_voteview_invalid_batch_preserves_staging(
    voteview_staging: Path, monkeypatch: pytest.MonkeyPatch, fetch: Mock
) -> None:
    monkeypatch.setattr(settings, "voteview_min_refetch_hours", 0)
    voteview_staging.write_text("previous snapshot")
    monkeypatch.setattr(voteview_senate_votes._session, "get", fetch)
    with pytest.raises(ValueError):
        voteview_senate_votes.run()
    assert voteview_staging.read_text() == "previous snapshot"


def test_partial_votes_are_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    house, lis, fallback = Mock(return_value=5), _blocked(), Mock(return_value=7)
    record = _patch_refresh(monkeypatch, house, lis, fallback)
    assert not asyncio.run(refresh._run_with_retry("votes", refresh.refresh_votes, delay=0))
    assert house.call_count == lis.call_count == fallback.call_count == 1
    record.assert_awaited_once_with("votes", 12, "partial", _FALLBACK_NOTE)


def test_fallback_reaches_normalizer_without_replaying_failed_house(
    voteview_staging: Path, house_staging: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the real pull -> normalize path, with fake HTTP and DB I/O."""
    house_staging.write_text("stale failed-chamber file must not even be parsed")
    monkeypatch.setattr(house_clerk_votes._session, "get", Mock(return_value=_Resp(403, b"blocked")))
    monkeypatch.setattr(senate_lis_votes._session, "get", Mock(return_value=_Resp(403, b"blocked")))
    fetch = _voteview()
    monkeypatch.setattr(voteview_senate_votes._session, "get", fetch)
    monkeypatch.setattr(vote_normalizer, "HOUSE_PATH", house_staging)
    monkeypatch.setattr(vote_normalizer, "SENATE_PATH", voteview_staging)
    record = AsyncMock()
    monkeypatch.setattr(refresh, "record_run", record)
    statements: list[object] = []

    class Session:
        async def __aenter__(self) -> Session:
            return self

        async def __aexit__(self, *_: object) -> None:
            pass

        async def execute(self, statement: object) -> Mock:
            statements.append(statement)
            return Mock(all=Mock(return_value=[]))

        async def commit(self) -> None:
            pass

    monkeypatch.setattr(vote_normalizer, "async_session_factory", Session)
    with pytest.raises(refresh.VoteRefreshIncompleteError):
        asyncio.run(refresh.refresh_votes())

    assert fetch.call_count == 3
    inserted = [
        statement for statement in statements
        if isinstance(statement, Insert) and statement.table.name == "votes"
    ]
    assert len(inserted) == 1
    params = inserted[0].compile(dialect=postgresql.dialect()).params
    assert {v for k, v in params.items() if k.startswith("vote_id_m")} == {"s119-2-1", "s119-2-2"}
    assert params["source_url_m0"] == "https://voteview.com/static/data/out/votes/S119_votes.csv"
    positions = [
        statement for statement in statements
        if isinstance(statement, Insert) and statement.table.name == "vote_positions"
    ]
    assert len(positions) == 1
    position_params = positions[0].compile(dialect=postgresql.dialect()).params
    member_ids = [v for k, v in position_params.items() if k.startswith("bioguide_id_m")]
    assert len(member_ids) == 7
    assert set(member_ids) == {"A000001", "B000002", "C000003", "D000004"}
    record.assert_awaited_once_with(
        "votes", 2, "partial", f"chamber(s) failed: house; {_FALLBACK_NOTE}"
    )
