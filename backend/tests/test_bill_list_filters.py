import asyncio
import os
from datetime import date
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.bill import Bill
from app.routers.bills import list_bills

_needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
_TABLES = [Bill.__table__]


def _bill(number: int, **fields: Any) -> Bill:
    return Bill(bill_id=f"hr{number}-119", congress=119, bill_type="hr", number=number, **fields)


@_needs_postgres
def test_became_law_filter_lists_only_enacted_bills_newest_action_first() -> None:
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
                session.add_all(
                    [
                        _bill(
                            1,
                            status="Became Law",
                            latest_action_date=date(2025, 3, 1),
                            update_date=date(2025, 3, 2),
                        ),
                        _bill(
                            2,
                            status="Became Law",
                            latest_action_date=date(2025, 6, 1),
                            update_date=date(2025, 1, 1),
                        ),
                        _bill(3, status="Became Law", update_date=date(2025, 7, 1)),
                        # Moving, but not enacted: excluded from the laws view.
                        _bill(
                            4,
                            latest_action="Passed House.",
                            latest_action_date=date(2025, 9, 1),
                            update_date=date(2025, 9, 1),
                        ),
                    ]
                )
                await session.commit()

            async with factory() as session:
                # Query() defaults only resolve inside FastAPI, so pass every
                # parameter explicitly when calling the endpoint directly.
                common: dict[str, Any] = {
                    "db": session,
                    "congress": None,
                    "bill_type": None,
                    "sponsor": None,
                    "policy_area": None,
                    "limit": 50,
                    "offset": 0,
                }
                laws = await list_bills(status="became_law", **common)
                assert [b.bill_id for b in laws] == ["hr2-119", "hr1-119", "hr3-119"]

                recent = await list_bills(status=None, **common)
                assert [b.bill_id for b in recent] == [
                    "hr4-119",
                    "hr3-119",
                    "hr1-119",
                    "hr2-119",
                ]

                paged = await list_bills(status="became_law", **{**common, "limit": 1, "offset": 1})
                assert [b.bill_id for b in paged] == ["hr1-119"]
        finally:
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: Base.metadata.drop_all(sync, tables=_TABLES)
                )
            await engine.dispose()

    asyncio.run(run())
