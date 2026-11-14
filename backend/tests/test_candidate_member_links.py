import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from app.services.candidate_identity import candidate_member_matches


def test_candidate_links_use_every_exact_id_without_office_or_name_inference() -> None:
    current = SimpleNamespace(
        bioguide_id="A000001", official_full_name="Different Profile Name", in_office=True
    )
    former = SimpleNamespace(
        bioguide_id="B000002", official_full_name="Former Profile", in_office=False
    )
    same_name = SimpleNamespace(
        bioguide_id="C000003", official_full_name="Unknown Candidate", in_office=True
    )
    result = Mock()
    result.all.return_value = [
        (current, ["S0CA00001", "H0CA00001", "H0CA00001"]),
        (former, ["H0CA00002"]),
        (same_name, ["H0CA00003"]),
    ]
    db = AsyncMock()
    db.execute.return_value = result
    matches = asyncio.run(
        candidate_member_matches(
            db, ["S0CA00001", "H0CA00001", "H0CA00002", "H0CA99999"]
        )
    )
    assert matches["S0CA00001"] == matches["H0CA00001"]
    profile = matches["H0CA00001"].profile
    assert profile is not None and profile.bioguide_id == "A000001"
    assert matches["H0CA00001"].status == "matched"
    assert matches["H0CA00002"].profile is not None
    assert matches["H0CA00002"].profile.in_office is False
    assert matches["H0CA99999"].status == "unmatched"
    assert matches["H0CA99999"].profile is None
    db.execute.assert_awaited_once()
    query = db.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "&&" in str(query)
    assert "official_full_name =" not in str(query)


def test_conflicting_crosswalk_matches_withhold_the_profile(
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = Mock()
    result.all.return_value = [
        (
            SimpleNamespace(
                bioguide_id=bioguide, official_full_name="Same Name", in_office=True
            ),
            ["H0CA00001"],
        )
        for bioguide in ("A000001", "B000002")
    ]
    db = AsyncMock()
    db.execute.return_value = result
    match = asyncio.run(candidate_member_matches(db, ["H0CA00001"]))["H0CA00001"]
    assert match.status == "ambiguous"
    assert match.profile is None
    assert "conflicting Bioguide matches" in caplog.text


def test_empty_candidate_page_does_not_query_the_crosswalk() -> None:
    db = AsyncMock()
    assert asyncio.run(candidate_member_matches(db, [])) == {}
    db.execute.assert_not_awaited()
