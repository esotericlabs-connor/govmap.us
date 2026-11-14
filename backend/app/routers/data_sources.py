"""Public data-pipeline status: every registered source, where it comes from,
and when it last refreshed successfully. Backs the /status page."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.pipeline_status import PipelineStatusRow
from app.schemas.data_sources import SourceEndpointOut, SourcesOut, SourceStatusOut
from app.sources import SOURCES

router = APIRouter(prefix="/api", tags=["sources"])


async def last_successes(db: AsyncSession) -> dict[str, datetime | None]:
    """Last successful refresh per source. Deliberately reads nothing else:
    run status and error detail stay on the authenticated /internal endpoints."""
    return {
        source: success
        for source, success in (
            await db.execute(select(PipelineStatusRow.source, PipelineStatusRow.last_success))
        ).all()
    }


async def build_sources(db: AsyncSession, *, now: datetime) -> SourcesOut:
    succeeded = await last_successes(db)
    return SourcesOut(
        generated_at=now,
        sources=[
            SourceStatusOut(
                name=spec.name,
                title=spec.title,
                publisher=spec.publisher,
                last_success=succeeded.get(spec.name),
                requires_key=spec.auth_env is not None,
                endpoints=[
                    SourceEndpointOut(url=e.url, official=e.official) for e in spec.endpoints
                ],
            )
            for spec in SOURCES.values()
        ],
    )


@router.get("/sources", response_model=SourcesOut)
async def sources(db: AsyncSession = Depends(get_db)) -> SourcesOut:
    """Registered data sources with their publishers, endpoints and last
    successful refresh."""
    return await build_sources(db, now=datetime.now(UTC))
