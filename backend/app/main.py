import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.body_limit import BodySizeLimitMiddleware
from app.config import settings
from app.logging_setup import setup_file_logging
from app.routers import (
    bills,
    campaign_money,
    committees,
    congress,
    data_sources,
    donations,
    elections,
    health,
    members,
    overview,
    pipeline_status,
    report,
    search,
    votes,
)
from app.scheduler import start_scheduler, stop_scheduler
from app.services.upstream import (
    UpstreamBudgetInitializingError,
    UpstreamBudgetUnavailableError,
    UpstreamCapacityError,
)

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_file_logging()
    scheduler_enabled = settings.scheduler_enabled
    if scheduler_enabled:
        start_scheduler()
    else:
        logger.info("scheduled pipeline refreshes disabled (SCHEDULER_ENABLED=false)")
    try:
        yield
    finally:
        if scheduler_enabled:
            stop_scheduler()


_docs_enabled = settings.api_docs_enabled
app = FastAPI(
    title="GovMap API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# Added before CORS so CORS stays the outer layer and a 413 still carries the
# CORS headers the browser needs to read it.
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # POST is needed only for /api/report (public bug reports); every other
    # route is GET. The browser preflight requires POST to be listed here.
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler for otherwise-unhandled errors: log the full traceback
    to app.log (via the `app` logger) and return a generic 500 that leaks no
    internals to the client. HTTPException/validation errors keep their own
    handlers — this only catches real 500s."""
    logger.error(
        "unhandled error on %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.exception_handler(UpstreamCapacityError)
async def upstream_capacity_handler(
    request: Request, exc: UpstreamCapacityError
) -> JSONResponse:
    if isinstance(exc, UpstreamBudgetInitializingError):
        detail = "Upstream request budget initializing; wait for the one-hour rollout hold"
    elif isinstance(exc, UpstreamBudgetUnavailableError):
        detail = "Upstream shared request budget unavailable; try again later"
    else:
        detail = "Upstream request capacity exhausted; try again later"
    return JSONResponse(
        status_code=503,
        content={"detail": detail},
        headers={"Retry-After": str(exc.retry_after)},
    )


app.include_router(members.router)
app.include_router(donations.router)
app.include_router(elections.router)
app.include_router(campaign_money.router)
app.include_router(committees.router)
app.include_router(bills.router)
app.include_router(votes.router)
app.include_router(search.router)
app.include_router(congress.router)
app.include_router(overview.router)
app.include_router(data_sources.router)
# Ops-only endpoints never appear in the published schema, even with docs on.
app.include_router(pipeline_status.router, include_in_schema=False)
app.include_router(report.router)
app.include_router(health.router)
