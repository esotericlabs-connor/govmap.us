import asyncio
import os
from datetime import date
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.bill import Bill
from app.normalize.member_sponsored import upsert_statement

_needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
_TABLES = [Bill.__table__]


def _index_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "bill_id": "hr1-119",
        "congress": 119,
        "bill_type": "hr",
        "number": 1,
        "title": None,
        "sponsor_bioguide_id": "A000001",
        "introduced_date": date(2025, 1, 3),
        "latest_action": "Referred to committee.",
        "latest_action_date": date(2025, 1, 3),
        "policy_area": None,
    }
    row.update(overrides)
    return row


@_needs_postgres
def test_sponsored_index_refresh_never_downgrades_a_bill() -> None:
    async def run() -> None:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            # This database belongs exclusively to the CI job, not the app.
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: Base.metadata.create_all(sync, tables=_TABLES)
                )
            async with factory() as session:
                session.add(
                    Bill(
                        bill_id="hr1-119",
                        congress=119,
                        bill_type="hr",
                        number=1,
                        title="Enriched title",
                        policy_area="Health",
                        latest_action="Passed House.",
                        latest_action_date=date(2025, 3, 1),
                    )
                )
                await session.commit()

            # A stale list entry with NULLs must not erase or rewind anything.
            async with factory() as session:
                await session.execute(
                    upsert_statement(
                        [_index_row(), _index_row(bill_id="hr2-119", number=2, title="Stub")]
                    )
                )
                await session.commit()
            async with factory() as session:
                kept = await session.get(Bill, "hr1-119")
                assert kept is not None
                assert (
                    kept.title,
                    kept.policy_area,
                    kept.latest_action,
                    kept.latest_action_date,
                    kept.sponsor_bioguide_id,
                ) == ("Enriched title", "Health", "Passed House.", date(2025, 3, 1), "A000001")
                added = await session.get(Bill, "hr2-119")
                assert added is not None and added.title == "Stub"

            # A newer action and newly known fields still move the row forward.
            async with factory() as session:
                await session.execute(
                    upsert_statement(
                        [
                            _index_row(
                                latest_action="Became Public Law.",
                                latest_action_date=date(2025, 4, 1),
                                policy_area="Taxation",
                            )
                        ]
                    )
                )
                await session.commit()
            async with factory() as session:
                moved = await session.get(Bill, "hr1-119")
                assert moved is not None
                assert (
                    moved.title,
                    moved.policy_area,
                    moved.latest_action,
                    moved.latest_action_date,
                ) == ("Enriched title", "Taxation", "Became Public Law.", date(2025, 4, 1))
        finally:
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: Base.metadata.drop_all(sync, tables=_TABLES)
                )
            await engine.dispose()

    asyncio.run(run())
