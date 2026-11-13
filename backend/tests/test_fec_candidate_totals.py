import asyncio
import hashlib
import io
import json
import os
import zipfile
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, call

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.models.campaign_money import (
    CampaignMoneyCoverage,
    CandidateCommitteeLink,
    CandidateFinanceSummary,
)
from app.models.crosswalk import IdCrosswalk
from app.models.election import ElectionCandidate
from app.models.member import Member
from app.normalize import campaign_money as normalizer
from app.pipelines import fec_candidate_totals as pipeline
from app.routers.campaign_money import candidate_money_detail, list_candidate_money
from app.schemas.campaign_money import CommitteeLinkOut, FecBulkFileRaw, FecCampaignMoneySnapshotRaw


def _summary(
    candidate_id: str = "H0CA00001",
    receipts: str = "123456789012.34",
    coverage_end: str = "10/14/2026",
) -> str:
    fields = [""] * 30
    fields[0] = candidate_id
    fields[1] = "Example Candidate"
    fields[2] = "C"
    fields[4] = "DEM"
    fields[5] = receipts
    fields[6] = ".01"
    fields[7] = "10.10"
    fields[8] = "-.04"
    fields[10] = "9.99"
    fields[16] = "0"
    fields[18] = "CA"
    fields[19] = "01"
    fields[27] = coverage_end
    return "|".join(fields)


def _link(
    subject_id: str = "H0CA00001",
    candidate_year: int = 2028,
    fec_year: int = 2026,
    linkage_id: int = 100,
) -> str:
    return f"{subject_id}|{candidate_year}|{fec_year}|C00000001|H|P|{linkage_id}"


def _zip(name: str, text: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, text)
    return output.getvalue()


def _mock_files(
    monkeypatch: pytest.MonkeyPatch,
    staging: Path,
    summaries: str,
    links: str,
) -> None:
    monkeypatch.setattr(settings, "fec_cycle", 2026)
    monkeypatch.setattr(pipeline, "STAGING_PATH", staging)

    def fake_download(cycle: int, filename: str) -> tuple[bytes, FecBulkFileRaw]:
        assert cycle == 2026
        if filename == "weball26.zip":
            body = _zip("weball26.txt", summaries)
        else:
            assert filename == "ccl26.zip"
            body = _zip("ccl.txt", links)
        return body, FecBulkFileRaw(
            name=filename,
            sha256=hashlib.sha256(body).hexdigest(),
            last_modified="2026-11-12T06:40:00Z",
        )

    monkeypatch.setattr(pipeline, "_download", fake_download)


def test_bulk_snapshot_preserves_exact_amounts_and_all_link_subjects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "money.json"
    _mock_files(
        monkeypatch,
        staging,
        _summary(),
        "\n".join([_link(), _link("C00000002", 2022, 2026, 101)]),
    )

    result = pipeline.run()
    staged = FecCampaignMoneySnapshotRaw.model_validate_json(staging.read_text(encoding="utf-8"))

    assert result.succeeded == staged.candidate_count == 1
    assert staged.linkage_count == 2
    assert staged.candidates[0].receipts == Decimal("123456789012.34")
    assert staged.candidates[0].transfers_from_authorized == Decimal("0.01")
    assert staged.candidates[0].transfers_to_authorized == Decimal("-0.04")
    assert staged.candidates[0].coverage_end == date(2026, 10, 14)
    assert staged.linkages[0].candidate_election_year == 2028
    assert staged.linkages[1].subject_id == "C00000002"
    assert staged.snapshot_revision == pipeline.snapshot_revision(staged.candidates, staged.linkages)
    assert json.loads(staging.read_text(encoding="utf-8"))["candidates"][0]["receipts"] == (
        "123456789012.34"
    )


@pytest.mark.parametrize(
    ("summaries", "links"),
    [
        ("\n".join([_summary(), _summary()]), _link()),
        (_summary("H0CA00001", "1.001"), _link()),
        (_summary("H0CA00001", "NaN"), _link()),
        (_summary("H0CA00001", "1.00", "2026-10-14"), _link()),
        (_summary(), "\n".join([_link(), _link(linkage_id=100)])),
        (_summary(), _link(fec_year=2024)),
        (_summary(), _link(candidate_year=-1)),
        (_summary(), _link(candidate_year=10000)),
        (_summary(), "not|a|link"),
    ],
)
def test_invalid_or_incomplete_files_do_not_replace_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    summaries: str,
    links: str,
) -> None:
    staging = tmp_path / "money.json"
    staging.write_text('{"previous":"snapshot"}', encoding="utf-8")
    _mock_files(monkeypatch, staging, summaries, links)

    with pytest.raises(pipeline.CampaignMoneySnapshotIncompleteError):
        pipeline.run()
    assert json.loads(staging.read_text(encoding="utf-8")) == {"previous": "snapshot"}


@pytest.mark.parametrize(("year", "outside_range"), [(2028, False), (2999, True), (0, True)])
def test_linkage_preserves_and_flags_unusual_source_years(year: int, outside_range: bool) -> None:
    link = pipeline._linkage_rows(_link(candidate_year=year), 2026)[0]
    output = CommitteeLinkOut.model_validate(link.model_dump())
    assert output.candidate_election_year == year
    assert output.model_dump()["candidate_election_year_outside_supported_range"] is outside_range


def test_archive_rejects_unexpected_entries_and_oversized_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(pipeline.CampaignMoneySnapshotIncompleteError, match="only"):
        pipeline._archive_text(_zip("wrong.txt", "data"), "ccl.txt")
    monkeypatch.setattr(pipeline, "_MAX_TEXT_BYTES", 3)
    with pytest.raises(pipeline.CampaignMoneySnapshotIncompleteError, match="size limit"):
        pipeline._archive_text(_zip("ccl.txt", "data"), "ccl.txt")


@pytest.mark.parametrize("redirect_status", [301, 302, 303, 307, 308])
def test_download_follows_only_the_expected_fec_archive_redirect(
    monkeypatch: pytest.MonkeyPatch, redirect_status: int
) -> None:
    filename = "weball26.zip"
    redirected_url = (
        "https://cg-519a459a-0ea3-42c2-b7bc-fa1143481f74."
        "s3-us-gov-west-1.amazonaws.com/bulk-downloads/2026/weball26.zip"
    )
    redirect = Mock(status_code=redirect_status, headers={"Location": redirected_url})
    result = Mock(
        status_code=200,
        headers={"Last-Modified": "Fri, 13 Nov 2026 06:37:33 GMT"},
    )
    get = Mock(side_effect=[redirect, result])
    slot = Mock(side_effect=lambda _source: nullcontext())
    read = Mock(return_value=b"archive")
    monkeypatch.setattr(pipeline.requests, "get", get)
    monkeypatch.setattr(pipeline, "request_slot", slot)
    monkeypatch.setattr(pipeline, "read_body", read)

    body, metadata = pipeline._download(2026, filename)

    assert body == b"archive"
    assert metadata.sha256 == hashlib.sha256(body).hexdigest()
    assert metadata.last_modified is not None
    assert slot.call_args_list == [call("fec"), call("fec")]
    assert get.call_args_list == [
        call(pipeline._file_url(2026, filename), timeout=45, stream=True, allow_redirects=False),
        call(redirected_url, timeout=45, stream=True, allow_redirects=False),
    ]
    read.assert_called_once_with(
        result, max_bytes=pipeline._MAX_ARCHIVE_BYTES, deadline_s=90, label=f"FEC {filename}"
    )
    redirect.close.assert_called_once()
    result.close.assert_called_once()


def test_download_also_accepts_a_direct_fec_archive_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock(status_code=200, headers={})
    get = Mock(return_value=response)
    slot = Mock(side_effect=lambda _source: nullcontext())
    monkeypatch.setattr(pipeline.requests, "get", get)
    monkeypatch.setattr(pipeline, "request_slot", slot)
    monkeypatch.setattr(pipeline, "read_body", Mock(return_value=b"archive"))

    body, metadata = pipeline._download(2026, "weball26.zip")

    assert body == b"archive"
    assert metadata.last_modified is None
    slot.assert_called_once_with("fec")
    get.assert_called_once()
    response.close.assert_called_once()


@pytest.mark.parametrize(
    "location",
    [
        None,
        "http://example.invalid/bulk-downloads/2026/weball26.zip",
        "https://example.invalid/bulk-downloads/2026/weball26.zip",
        f"{pipeline._ARCHIVE_REDIRECT_ROOT}/2026/ccl26.zip",
        f"{pipeline._ARCHIVE_REDIRECT_ROOT}/2026/weball26.zip?other=1",
    ],
)
def test_download_rejects_unexpected_fec_redirects(
    monkeypatch: pytest.MonkeyPatch, location: str | None
) -> None:
    redirect = Mock(status_code=302, headers={"Location": location})
    get = Mock(return_value=redirect)
    monkeypatch.setattr(pipeline.requests, "get", get)
    monkeypatch.setattr(pipeline, "request_slot", lambda _source: nullcontext())

    with pytest.raises(
        pipeline.CampaignMoneySnapshotIncompleteError, match="unexpected archive redirect"
    ):
        pipeline._download(2026, "weball26.zip")
    get.assert_called_once()
    redirect.close.assert_called_once()


def test_download_rejects_a_second_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"{pipeline._ARCHIVE_REDIRECT_ROOT}/2026/weball26.zip"
    first = Mock(status_code=302, headers={"Location": url})
    second = Mock(status_code=302, headers={"Location": url})
    get = Mock(side_effect=[first, second])
    monkeypatch.setattr(pipeline.requests, "get", get)
    monkeypatch.setattr(pipeline, "request_slot", lambda _source: nullcontext())

    with pytest.raises(
        pipeline.CampaignMoneySnapshotIncompleteError, match="unexpected archive redirect"
    ):
        pipeline._download(2026, "weball26.zip")
    assert get.call_count == 2
    first.close.assert_called_once()
    second.close.assert_called_once()


def test_normalizer_rejects_a_modified_snapshot_before_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "money.json"
    _mock_files(monkeypatch, staging, _summary(), _link())
    pipeline.run()
    snapshot = json.loads(staging.read_text(encoding="utf-8"))
    snapshot["candidates"][0]["receipts"] = "1.00"
    staging.write_text(json.dumps(snapshot), encoding="utf-8")

    with pytest.raises(ValueError, match="revision does not match"):
        asyncio.run(normalizer.load_campaign_money(staging))


_needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
_TABLES = [
    Member.__table__,
    IdCrosswalk.__table__,
    CandidateFinanceSummary.__table__,
    CandidateCommitteeLink.__table__,
    CampaignMoneyCoverage.__table__,
    ElectionCandidate.__table__,
]


@_needs_postgres
@pytest.mark.parametrize(
    "fail_table",
    ["candidate_finance_summaries", "candidate_committee_links", "campaign_money_coverage"],
)
def test_atomic_money_snapshot_and_period_qualified_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_table: str
) -> None:
    staging = tmp_path / "money.json"
    summaries = "\n".join(
        [
            _summary("H0CA00001", "100.01"),
            _summary("H0CA00002", "100.02"),
            _summary("H0CA00003", "99999999999.99", "09/30/2026"),
        ]
    )
    links = "\n".join([_link(), _link("C00000002", 2022, 2026, 101)])
    _mock_files(monkeypatch, staging, summaries, links)
    pipeline.run()
    staged = json.loads(staging.read_text(encoding="utf-8"))
    staged["fetched_at"] = "2026-11-12T07:00:00Z"
    staging.write_text(json.dumps(staged), encoding="utf-8")

    async def scenario() -> None:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(normalizer, "async_session_factory", factory)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=_TABLES))
            assert await normalizer.load_campaign_money(staging) == 3
            async with factory() as session:
                session.add(
                    Member(
                        bioguide_id="A000001",
                        first_name="Different",
                        last_name="Name",
                        official_full_name="Different Profile Name",
                        chamber="senate",
                        state="CA",
                        party="Independent",
                        term_start=date(2025, 1, 3),
                        fec_candidate_ids=["H0CA00001"],
                        in_office=True,
                    )
                )
                await session.flush()
                session.add(
                    IdCrosswalk(
                        bioguide_id="A000001", fec_ids=["S0CA00001", "H0CA00001"]
                    )
                )
                session.add(
                    ElectionCandidate(
                        finance_cycle=2026,
                        candidate_id="H0CA00001",
                        name="Example Candidate",
                        office="H",
                        state="CA",
                        district="01",
                        cycles=[2026],
                        election_years=[2028],
                        principal_committees=[],
                    )
                )
                await session.commit()

            async with factory() as session:
                result = await list_candidate_money(
                    db=session,
                    cycle=2026,
                    office="H",
                    state="CA",
                    district="01",
                    q=None,
                    through=None,
                    limit=20,
                    offset=0,
                )
                assert result.available
                assert result.matching_count == 3
                assert result.filtered_count == 2
                assert result.selected_date == date(2026, 10, 14)
                assert [row.candidate_id for row in result.candidates] == [
                    "H0CA00002",
                    "H0CA00001",
                ]
                assert result.model_dump(mode="json")["candidates"][0]["receipts"] == "100.02"
                matched = result.candidates[1].member_match
                assert matched is not None and matched.status == "matched"
                assert matched.profile is not None
                assert matched.profile.bioguide_id == "A000001"
                unmatched = result.candidates[0].member_match
                assert unmatched is not None and unmatched.status == "unmatched"

            async with factory() as session:
                earlier = await list_candidate_money(
                    db=session,
                    cycle=2026,
                    office="H",
                    state="CA",
                    district="01",
                    q=None,
                    through=date(2026, 9, 30),
                    limit=20,
                    offset=0,
                )
                assert earlier.filtered_count == 1
                assert earlier.candidates[0].receipts == Decimal("99999999999.99")

            async with factory() as session:
                literal = await list_candidate_money(
                    db=session,
                    cycle=2026,
                    office="H",
                    state=None,
                    district=None,
                    q="%",
                    through=None,
                    limit=20,
                    offset=0,
                )
                assert literal.matching_count == 0

            for query, expected in [
                ("cand examp", 3),
                ("EXAMP, cand", 3),
                ("cand unknown", 0),
                ("h0ca00001", 1),
            ]:
                async with factory() as session:
                    found = await list_candidate_money(
                        db=session,
                        cycle=2026,
                        office="H",
                        state=None,
                        district=None,
                        q=query,
                        through=None,
                        limit=20,
                        offset=0,
                    )
                    assert found.matching_count == expected

            async with factory() as session:
                detail = await candidate_money_detail(
                    candidate_id="H0CA00001", cycle=2026, limit=50, offset=0, db=session
                )
                assert detail.catalog_match is not None
                assert detail.catalog_match.election_years == [2028]
                assert detail.linkage_count == 1
                assert detail.filtered_linkage_count == 1
                assert detail.linkages[0].candidate_election_year == 2028
                assert detail.linkages[0].fec_election_year == 2026
                assert detail.candidate.transfers_from_authorized == Decimal("0.01")
                assert detail.candidate.member_match == matched

            async with factory() as session:
                filtered = await candidate_money_detail(
                    candidate_id="H0CA00001", cycle=2026, limit=1, offset=0,
                    q="C99999999", sort="committee", db=session,
                )
                assert filtered.linkage_count == 1
                assert filtered.filtered_linkage_count == 0
                assert filtered.linkages == []

            async with factory() as session:
                named = await list_candidate_money(
                    db=session, cycle=2026, office="H", state="CA", district="01",
                    q=None, through=date(2026, 10, 14), sort="name", limit=1, offset=1,
                )
                assert named.filtered_count == 2
                assert [row.candidate_id for row in named.candidates] == ["H0CA00002"]

            def fail_insert(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
                if statement.startswith(f"INSERT INTO {fail_table}"):
                    raise RuntimeError("simulated interrupted load")

            event.listen(engine.sync_engine, "before_cursor_execute", fail_insert)
            try:
                with pytest.raises(RuntimeError, match="interrupted load"):
                    await normalizer.load_campaign_money(staging)
            finally:
                event.remove(engine.sync_engine, "before_cursor_execute", fail_insert)
            async with factory() as session:
                preserved = (
                    await session.execute(
                        select(CandidateFinanceSummary).where(
                            CandidateFinanceSummary.candidate_id == "H0CA00001"
                        )
                    )
                ).scalar_one()
                assert preserved.receipts == Decimal("100.01")
                preserved_links = (
                    await session.execute(select(CandidateCommitteeLink))
                ).scalars().all()
                assert {link.linkage_id for link in preserved_links} == {100, 101}
                preserved_coverage = (
                    await session.execute(
                        select(CampaignMoneyCoverage).where(
                            CampaignMoneyCoverage.finance_cycle == 2026
                        )
                    )
                ).scalar_one()
                assert preserved_coverage.candidate_count == 3
                assert preserved_coverage.linkage_count == 2
        finally:
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.drop_all(sync, tables=_TABLES))
            await engine.dispose()

    asyncio.run(scenario())
