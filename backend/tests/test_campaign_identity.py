import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from app.schemas.member import CandidateMemberMatchOut, CandidateMemberProfileOut
from app.services import campaign_identity


def _match(bioguide: str) -> CandidateMemberMatchOut:
    return CandidateMemberMatchOut(
        status="matched",
        profile=CandidateMemberProfileOut(
            bioguide_id=bioguide, official_full_name="Example Member", in_office=True
        ),
    )


@pytest.mark.parametrize("status", ["unmatched", "ambiguous"])
def test_current_candidate_cycles_do_not_require_a_member_profile(status: str) -> None:
    db = AsyncMock()
    summaries = Mock()
    summaries.all.return_value = [("H0CA00001", 2026)]
    db.execute.return_value = summaries
    match = CandidateMemberMatchOut.model_validate({"status": status})
    result = asyncio.run(campaign_identity.related_candidate_finances(db, "H0CA00001", match))
    assert result.model_dump() == {
        "candidates": [{"candidate_id": "H0CA00001", "finance_cycles": [2026]}],
        "withheld_count": 0,
    }
    db.execute.assert_awaited_once()


def test_related_candidates_withhold_invalid_and_conflicting_ids(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    crosswalk = Mock()
    crosswalk.scalar_one.return_value = [
        "H0CA00001",
        "H0CA00002",
        "H0CA00002",
        "H0CA00003",
        "S0CA00001",
        "bad-id",
    ]
    summaries = Mock()
    summaries.all.return_value = [
        ("H0CA00001", 2026),
        ("H0CA00002", 2026),
        ("H0CA00002", 2024),
    ]
    db = AsyncMock()
    db.execute.side_effect = [crosswalk, summaries]
    matches = AsyncMock(
        return_value={
            "H0CA00002": _match("A000001"),
            "H0CA00003": CandidateMemberMatchOut(status="ambiguous"),
            "S0CA00001": _match("A000001"),
        }
    )
    monkeypatch.setattr(campaign_identity, "candidate_member_matches", matches)

    related = asyncio.run(
        campaign_identity.related_candidate_finances(db, "H0CA00001", _match("A000001"))
    )

    assert related is not None
    assert related.model_dump() == {
        "candidates": [
            {"candidate_id": "H0CA00001", "finance_cycles": [2026]},
            {"candidate_id": "H0CA00002", "finance_cycles": [2026, 2024]},
            {"candidate_id": "S0CA00001", "finance_cycles": []},
        ],
        "withheld_count": 2,
    }
    assert "Withholding 1 invalid FEC IDs" in caplog.text
    matches.assert_awaited_once_with(db, ["H0CA00002", "H0CA00003", "S0CA00001"])
    assert db.execute.await_count == 2


def test_current_id_is_retained_when_there_are_no_other_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crosswalk = Mock()
    crosswalk.scalar_one.return_value = ["H0CA00001"]
    summaries = Mock()
    summaries.all.return_value = [("H0CA00001", 2026)]
    db = AsyncMock()
    db.execute.side_effect = [crosswalk, summaries]
    matches = AsyncMock(return_value={})
    monkeypatch.setattr(campaign_identity, "candidate_member_matches", matches)

    related = asyncio.run(
        campaign_identity.related_candidate_finances(db, "H0CA00001", _match("A000001"))
    )

    assert related is not None
    assert related.model_dump()["candidates"] == [
        {"candidate_id": "H0CA00001", "finance_cycles": [2026]}
    ]
    assert related.withheld_count == 0
    assert db.execute.await_count == 2


def test_inconsistent_matched_profile_fails_explicitly() -> None:
    db = AsyncMock()
    with pytest.raises(RuntimeError, match="missing its member profile"):
        asyncio.run(
            campaign_identity.related_candidate_finances(
                db, "H0CA00001", CandidateMemberMatchOut(status="matched")
            )
        )
    db.execute.assert_not_awaited()

    crosswalk = Mock()
    crosswalk.scalar_one.return_value = ["H0CA00002"]
    db.execute.return_value = crosswalk
    with pytest.raises(RuntimeError, match="missing from its crosswalk"):
        asyncio.run(
            campaign_identity.related_candidate_finances(db, "H0CA00001", _match("A000001"))
        )
