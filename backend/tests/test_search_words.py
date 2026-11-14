import asyncio
import os
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import literal, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.bill import Bill
from app.models.committee import Committee
from app.models.crosswalk import IdCrosswalk
from app.models.election import ElectionCandidate, ElectionCatalogCoverage
from app.models.member import Member
from app.models.vote import Vote
from app.routers.elections import list_election_candidates
from app.routers.search import search
from app.services.candidate_identity import candidate_member_matches
from app.services.search import match_words


def test_word_patterns_are_bound_and_metacharacters_are_literal() -> None:
    statement = select(literal("example")).where(
        match_words("CROCKETT,  jas\t100%_\\", Member.official_full_name)
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    assert {"%CROCKETT%", "%jas%", "%100\\%\\_\\\\%"}.issubset(compiled.params.values())
    assert "ESCAPE" in str(compiled)
    assert "CROCKETT" not in str(compiled)


def test_short_global_search_does_not_query_the_database() -> None:
    db = AsyncMock()
    result = asyncio.run(search(q=" a ", db=db))
    assert all(not result[group] for group in ("members", "bills", "votes", "committees"))
    db.execute.assert_not_awaited()


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
def test_word_matching_against_postgres() -> None:
    async def scenario() -> None:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        cases = [
            ("CROCKETT jas", "Jasmine Crockett", True),
            ("jas crockett", "Jasmine Crockett", True),
            (" Crockett,\tJAS ", "Jasmine Crockett", True),
            ("crockett unknown", "Jasmine Crockett", False),
            ("jas jas", "Jasmine Crockett", True),
            ("fair tax", "Tax Fairness Act", True),
            ("tax fair", "Tax Fairness Act", True),
            ("100%", "100% Fair Tax", True),
            ("100%", "1000 Fair Tax", False),
            ("a_b", "a_b policy", True),
            ("a_b", "axb policy", False),
            ("a\\b", "a\\b policy", True),
            ("a\\b", "ab policy", False),
            (",,", "anything", False),
            ("  ", "anything", False),
            ("jas", None, False),
        ]
        try:
            async with engine.connect() as connection:
                for term, value, expected in cases:
                    found = (
                        await connection.execute(select(match_words(term, literal(value))))
                    ).scalar_one()
                    assert bool(found) is expected, (term, value)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
def test_global_search_and_exact_member_identity_against_postgres() -> None:
    tables = [
        Member.__table__, IdCrosswalk.__table__, Bill.__table__,
        Vote.__table__, Committee.__table__,
        ElectionCandidate.__table__, ElectionCatalogCoverage.__table__,
    ]

    async def scenario() -> None:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
            async with factory.begin() as session:
                session.add_all(
                    [
                        Member(
                            bioguide_id=bioguide,
                            first_name=first_name,
                            last_name="Crockett",
                            official_full_name=f"{first_name} Crockett",
                            chamber="senate" if bioguide == "A000001" else "house",
                            state="TX",
                            party="Independent",
                            term_start=date(2025, 1, 3),
                            in_office=in_office,
                        )
                        for bioguide, first_name, in_office in [
                            ("A000001", "Jasmine", True),
                            ("B000002", "Jordan", True),
                            ("C000003", "Jasmine", False),
                        ]
                    ]
                )
                await session.flush()
                session.add_all(
                    [
                        IdCrosswalk(
                            bioguide_id="A000001",
                            fec_ids=["S0TX00001", "H2TX30178", "H0TX00002"],
                        ),
                        IdCrosswalk(bioguide_id="B000002", fec_ids=["H0TX00002"]),
                        IdCrosswalk(bioguide_id="C000003", fec_ids=["H0TX00003"]),
                        Bill(
                            bill_id="hr1234-119", congress=119, bill_type="hr",
                            number=1234, title="Fair Tax Act",
                        ),
                        Vote(
                            vote_id="h119-2-1", chamber="house", congress=119,
                            session=2, roll_number=1, question="Passage of the Fair Tax Act",
                        ),
                        Committee(
                            committee_id="HSTX", name="Committee on Fair Tax Policy", chamber="house"
                        ),
                        ElectionCatalogCoverage(
                            finance_cycle=2026, complete=True, candidate_count=2,
                            expected_count=2, page_count=1, snapshot_revision="a" * 64,
                            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
                        ),
                        ElectionCandidate(
                            finance_cycle=2026, candidate_id="H2TX30178",
                            name="CROCKETT, JASMINE", office="H", state="TX", district="30",
                        ),
                        ElectionCandidate(
                            finance_cycle=2026, candidate_id="H0CA00001",
                            name="ALPHA, EXAMPLE", office="H", state="CA", district="01",
                        ),
                    ]
                )
            async with factory() as session:
                for query in ("CROCKETT jas", "jas crockett", "CROCKETT,  jas", "Jasmine"):
                    response = await search(q=query, db=session)
                    assert [member["bioguide_id"] for member in response["members"]] == [
                        "A000001", "C000003"
                    ]
                for query in ("h2tx30178", "S0TX00001", "a000001"):
                    response = await search(q=query, db=session)
                    assert [member["bioguide_id"] for member in response["members"]] == ["A000001"]
                for query in ("tx", "Crockett"):
                    assert len((await search(q=query, db=session))["members"]) == 3
                for query in ("Crockett unknown", "100%", ",,"):
                    response = await search(q=query, db=session)
                    assert all(
                        not response[group] for group in ("members", "bills", "votes", "committees")
                    )
                for query in ("tax fair", "fair tax"):
                    response = await search(q=query, db=session)
                    assert len(response["bills"]) == len(response["votes"]) == len(
                        response["committees"]
                    ) == 1
                for query in ("hr 1234", "1234 hr"):
                    response = await search(q=query, db=session)
                    assert [bill["bill_id"] for bill in response["bills"]] == ["hr1234-119"]
                matches = await candidate_member_matches(
                    session,
                    ["H2TX30178", "S0TX00001", "H0TX00002", "H0TX00003", "H0TX99999"],
                )
                assert matches["H2TX30178"] == matches["S0TX00001"]
                profile = matches["H2TX30178"].profile
                assert profile is not None and profile.bioguide_id == "A000001"
                assert matches["H0TX00002"].status == "ambiguous"
                assert matches["H0TX00002"].profile is None
                former = matches["H0TX00003"].profile
                assert former is not None and former.in_office is False
                assert matches["H0TX99999"].status == "unmatched"
            for query, expected in [
                ("jas crockett", 1),
                ("CROCKETT, jas", 1),
                ("h2tx30178", 1),
                ("crockett unknown", 0),
                ("%", 0),
            ]:
                async with factory() as session:
                    response = await list_election_candidates(
                        db=session, cycle=2026, election_year=None, office=None,
                        state=None, district=None, party=None, q=query, limit=50, offset=0,
                    )
                    assert response.filtered_count == expected
                    assert len(response.candidates) == expected
                    if expected:
                        assert response.candidates[0].member_match == matches["H2TX30178"]
            async with factory() as session:
                page = await list_election_candidates(
                    db=session, cycle=2026, election_year=None, office=None, state=None,
                    district=None, party=None, q=None, sort="name", limit=1, offset=1,
                )
                assert page.filtered_count == 2
                assert [candidate.candidate_id for candidate in page.candidates] == ["H2TX30178"]
        finally:
            try:
                async with engine.begin() as connection:
                    await connection.run_sync(
                        lambda sync: Base.metadata.drop_all(sync, tables=tables)
                    )
            finally:
                await engine.dispose()

    asyncio.run(scenario())
