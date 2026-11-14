import asyncio
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.pipeline_status import PipelineStatusRow
from app.routers.data_sources import build_sources
from app.sources import SOURCES

_needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
_TABLES = [PipelineStatusRow.__table__]
_NOW = datetime(2026, 11, 12, 15, tzinfo=UTC)


@_needs_postgres
def test_sources_report_registry_and_last_success_only() -> None:
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
                        PipelineStatusRow(
                            source="votes",
                            last_success=datetime(2026, 11, 12, 6, tzinfo=UTC),
                            record_count=42,
                            status="error",
                            detail="internal detail",
                        ),
                        PipelineStatusRow(
                            source="not_a_registered_source",
                            last_success=datetime(2026, 11, 12, 6, tzinfo=UTC),
                            status="ok",
                        ),
                    ]
                )
                await session.commit()
                result = await build_sources(session, now=_NOW)

            assert result.generated_at == _NOW
            assert [s.name for s in result.sources] == list(SOURCES)
            by_name = {s.name: s for s in result.sources}
            assert by_name["votes"].last_success == datetime(2026, 11, 12, 6, tzinfo=UTC)
            assert by_name["congress_gov_bills"].last_success is None
            assert by_name["congress_gov_bills"].requires_key is True
            assert by_name["congress_legislators"].requires_key is False
            assert [e.url for e in by_name["votes"].endpoints] == [
                e.url for e in SOURCES["votes"].endpoints
            ]
            # Run status, record counts and error detail stay on the
            # authenticated /internal endpoints.
            dumped = result.model_dump()
            assert set(dumped["sources"][0]) == {
                "name",
                "title",
                "publisher",
                "last_success",
                "requires_key",
                "endpoints",
            }
            assert "internal detail" not in str(dumped)
        finally:
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: Base.metadata.drop_all(sync, tables=_TABLES)
                )
            await engine.dispose()

    asyncio.run(run())


def test_no_endpoint_exposes_a_credential() -> None:
    for spec in SOURCES.values():
        for endpoint in spec.endpoints:
            assert "?" not in endpoint.url and "@" not in endpoint.url, spec.name
