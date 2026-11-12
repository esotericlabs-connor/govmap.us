import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import requests
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.models.bill import Bill, BillAction, BillText, Cosponsor
from app.normalize import bills as normalizer
from app.routers import bills as routes
from app.services import bill_enrich

OLD = datetime(2025, 1, 3, tzinfo=UTC)
NEW = datetime(2025, 2, 3, tzinfo=UTC)
BILL_ID = "hr1-119"
TEXT_URL = "https://www.congress.gov/119/bills/hr1/BILLS-119hr1rh.htm"
_TABLES = [Bill.__table__, BillAction.__table__, Cosponsor.__table__, BillText.__table__]
_needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)


@asynccontextmanager
async def _database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=_TABLES))
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.drop_all(sync, tables=_TABLES))
        await engine.dispose()


async def _seed(
    factory: async_sessionmaker[AsyncSession],
    *,
    cached_revision: datetime | None = None,
    enriched: bool = True,
) -> None:
    async with factory() as db:
        db.add(
            Bill(
                bill_id=BILL_ID, congress=119, bill_type="hr", number=1,
                title="Original title", enriched_at=OLD if enriched else None, updated_at=OLD,
            )
        )
        await db.flush()
        db.add(
            BillText(
                bill_id=BILL_ID, plain="Old text", text_version="Introduced in House",
                truncated=True, fetched_at=OLD, bill_revision_at=cached_revision,
            )
        )
        await db.commit()


def _versions() -> dict[str, Any]:
    return {
        "textVersions": [
            {
                "type": "Reported in House", "date": "2025-02-03",
                "formats": [{"type": "Formatted Text", "url": TEXT_URL}],
            },
            {
                "type": "Enrolled", "date": "2025-02-04",
                "formats": [{"type": "PDF", "url": TEXT_URL.replace("rh.htm", "enr.pdf")}],
            },
        ]
    }


@_needs_postgres
@pytest.mark.parametrize("enriched", [True, False], ids=["enriched", "index-stub"])
def test_legacy_cache_is_refreshed_then_reused_without_a_key(
    monkeypatch: pytest.MonkeyPatch, enriched: bool,
) -> None:
    async def run() -> None:
        async with _database() as factory:
            await _seed(factory, enriched=enriched)
            async with factory() as db:
                async def upstream(_source: str, fn: Any, *_args: Any) -> Any:
                    assert not db.in_transaction()
                    return _versions() if fn is bill_enrich._get else ("<pre>New text</pre>", False)

                fetch = AsyncMock(side_effect=upstream)
                monkeypatch.setattr(bill_enrich, "run_upstream", fetch)
                monkeypatch.setattr(settings, "congress_gov_api_key", "test-placeholder")
                payload = await bill_enrich.get_bill_text(db, BILL_ID)
                assert payload is not None and payload["plain"] == "New text"
                assert payload["truncated"] is False
                assert payload["source_url"] == TEXT_URL
                assert payload["text_version"] == "Reported in House"
                row = await db.get(BillText, BILL_ID)
                assert row is not None and row.bill_revision_at == OLD and row.fetched_at > OLD
                assert fetch.await_count == 2
            async with factory() as db:
                monkeypatch.setattr(settings, "congress_gov_api_key", "")
                assert await bill_enrich.get_bill_text(db, BILL_ID) == payload
                assert fetch.await_count == 2

    asyncio.run(run())


@_needs_postgres
def test_normalizer_refresh_invalidates_text_and_rereads_the_identity_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    staged = tmp_path / "bills_raw.json"
    staged.write_text(
        json.dumps(
            [{
                "bill": {"congress": 119, "type": "HR", "number": 1, "title": "Updated title"},
                "text_versions": _versions()["textVersions"],
                "actions": [], "cosponsors": [], "summaries": [],
            }]
        )
    )

    async def run() -> None:
        async with _database() as factory:
            await _seed(factory, cached_revision=OLD)
            monkeypatch.setattr(normalizer, "async_session_factory", factory)
            monkeypatch.setattr(normalizer, "STAGING_PATH", staged)
            fetch = AsyncMock(side_effect=[_versions(), ("<pre>Updated body</pre>", False)])
            monkeypatch.setattr(bill_enrich, "run_upstream", fetch)
            monkeypatch.setattr(settings, "congress_gov_api_key", "test-placeholder")
            async with factory() as db:
                previous = await bill_enrich.get_bill_text(db, BILL_ID)
                assert previous is not None and previous["plain"] == "Old text"
                await db.commit()
                assert await normalizer.normalize_and_load() == 1
                payload = await bill_enrich.get_bill_text(db, BILL_ID)
                assert payload is not None and payload["plain"] == "Updated body"
                bill = await db.get(Bill, BILL_ID)
                text = await db.get(BillText, BILL_ID)
                assert bill is not None and text is not None
                assert text.bill_revision_at == bill.enriched_at != OLD
                assert bill.title == "Updated title"
                assert bill.text_version == "Enrolled"
                assert text.text_version == "Reported in House"
                assert await bill_enrich.get_bill_text(db, BILL_ID) == payload
                assert fetch.await_count == 2

    asyncio.run(run())


@_needs_postgres
def test_on_demand_enrichment_invalidates_a_stub_text_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        async with _database() as factory:
            await _seed(factory, cached_revision=OLD, enriched=False)
            bundle = {
                "bill": {"congress": 119, "type": "HR", "number": 1, "title": "Enriched"},
                "text_versions": _versions()["textVersions"],
            }
            fetch = AsyncMock(
                side_effect=[bundle, _versions(), ("<pre>Enriched text</pre>", False)]
            )
            monkeypatch.setattr(bill_enrich, "run_upstream", fetch)
            monkeypatch.setattr(settings, "congress_gov_api_key", "test-placeholder")
            async with factory() as db:
                assert await bill_enrich.enrich_bill(db, BILL_ID)
                payload = await bill_enrich.get_bill_text(db, BILL_ID)
                assert payload is not None and payload["plain"] == "Enriched text"
                assert fetch.await_count == 3

    asyncio.run(run())


@_needs_postgres
def test_failed_refresh_does_not_serve_or_erase_stale_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        async with _database() as factory:
            await _seed(factory)
            fetch = AsyncMock(side_effect=[_versions(), requests.Timeout("test outage")])
            monkeypatch.setattr(bill_enrich, "run_upstream", fetch)
            monkeypatch.setattr(settings, "congress_gov_api_key", "test-placeholder")
            async with factory() as db:
                assert await bill_enrich.get_bill_text(db, BILL_ID) is None
            async with factory() as db:
                row = await db.get(BillText, BILL_ID)
                assert row is not None and row.plain == "Old text"
                assert row.bill_revision_at is None and row.fetched_at == OLD

    asyncio.run(run())


@_needs_postgres
@pytest.mark.parametrize("refresh_bill", [True, False], ids=["new-revision", "same-revision"])
def test_late_fetch_cannot_overwrite_a_concurrent_winner(
    monkeypatch: pytest.MonkeyPatch, refresh_bill: bool,
) -> None:
    async def run() -> None:
        async with _database() as factory:
            await _seed(factory)
            started, release = asyncio.Event(), asyncio.Event()

            async def upstream(_source: str, fn: Any, *_args: Any) -> Any:
                if fn is bill_enrich._get:
                    return _versions()
                if asyncio.current_task() is old:
                    started.set()
                    await release.wait()
                    return "<pre>Late old response</pre>", False
                return "<pre>Winning new response</pre>", False

            async def fetch() -> dict | None:
                async with factory() as db:
                    return await bill_enrich.get_bill_text(db, BILL_ID)

            monkeypatch.setattr(bill_enrich, "run_upstream", upstream)
            monkeypatch.setattr(settings, "congress_gov_api_key", "test-placeholder")
            old = asyncio.create_task(fetch())
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                if refresh_bill:
                    async with factory() as db:
                        bill = await db.get(Bill, BILL_ID)
                        assert bill is not None
                        bill.enriched_at = NEW
                        await db.commit()
                winner = await asyncio.wait_for(fetch(), timeout=5)
                assert winner is not None and winner["plain"] == "Winning new response"
                release.set()
                if refresh_bill:
                    with pytest.raises(bill_enrich.BillTextChangedError):
                        await asyncio.wait_for(old, timeout=5)
                else:
                    assert await asyncio.wait_for(old, timeout=5) == winner
                async with factory() as db:
                    row = await db.get(BillText, BILL_ID)
                    assert row is not None and row.plain == "Winning new response"
                    assert row.bill_revision_at == (NEW if refresh_bill else OLD)
            finally:
                release.set()
                if not old.done():
                    old.cancel()
                await asyncio.gather(old, return_exceptions=True)

    asyncio.run(run())


def test_concurrent_bill_change_is_a_retryable_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes, "get_bill_text", AsyncMock(side_effect=bill_enrich.BillTextChangedError(BILL_ID))
    )
    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.bill_full_text(BILL_ID, SimpleNamespace()))
    assert caught.value.status_code == 503
    assert caught.value.headers == {"Retry-After": "1"}
