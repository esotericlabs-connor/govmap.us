import asyncio
import os
from datetime import date
from typing import Literal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.vote import Vote
from app.routers.votes import list_votes

_needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)


@_needs_postgres
def test_vote_search_sort_and_paging_cover_the_filtered_dataset() -> None:
    async def scenario() -> None:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        tables = [Vote.__table__]
        try:
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
            async with factory() as db, db.begin():
                db.add_all([
                    Vote(
                        vote_id="h119-1-1", chamber="house", congress=119, session=1,
                        roll_number=1, question="Zulu Fair Tax Act", date=date(2025, 1, 1),
                        result="Passed", bill_id="hr1-119",
                    ),
                    Vote(
                        vote_id="h119-1-2", chamber="house", congress=119, session=1,
                        roll_number=2, question="Alpha Fair Tax Act", date=date(2025, 2, 1),
                    ),
                    Vote(
                        vote_id="s119-1-1", chamber="senate", congress=119, session=1,
                        roll_number=1, question="Unrelated motion", date=date(2025, 3, 1),
                    ),
                    Vote(
                        vote_id="h119-1-3", chamber="house", congress=119, session=1,
                        roll_number=3, question=None, date=None,
                    ),
                ])
            async with factory() as db:
                async def query(
                    q: str | None = None,
                    sort: Literal["recent", "oldest", "question"] = "recent", offset: int = 0,
                    limit: int = 50,
                ) -> list[Vote]:
                    return await list_votes(
                        db=db, chamber=None, congress=None, session=None, bill_id=None,
                        q=q, sort=sort, offset=offset, limit=limit,
                    )

                assert [row.vote_id for row in await query()] == [
                    "s119-1-1", "h119-1-2", "h119-1-1", "h119-1-3"
                ]
                assert [row.vote_id for row in await query("tax fair", "question", 1, 1)] == [
                    "h119-1-1"
                ]
                assert [row.vote_id for row in await query(sort="oldest")] == [
                    "h119-1-1", "h119-1-2", "s119-1-1", "h119-1-3"
                ]
                assert [row.vote_id for row in await query("passed hr1")] == ["h119-1-1"]
                for value in ("tax unknown", "%", "_"):
                    assert await query(value) == []
        finally:
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.drop_all(sync, tables=tables))
            await engine.dispose()

    asyncio.run(scenario())
