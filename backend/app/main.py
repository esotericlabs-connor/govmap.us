import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.logging_setup import setup_file_logging
from app.routers import (
    bills,
    committees,
    congress,
    donations,
    members,
    pipeline_status,
    report,
    search,
    votes,
)
from app.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_file_logging()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="GovMap API", version="0.1.0", lifespan=lifespan)

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


app.include_router(members.router)
app.include_router(donations.router)
app.include_router(committees.router)
app.include_router(bills.router)
app.include_router(votes.router)
app.include_router(search.router)
app.include_router(congress.router)
app.include_router(pipeline_status.router)
app.include_router(report.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
