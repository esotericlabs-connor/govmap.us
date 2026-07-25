"""Public bug-report endpoint → appends to bug_reports.log.

`POST /api/report` takes a category/subcategory (validated against a fixed
allowlist, so those fields can never be an injection vector), a free-text
message, and the page URL. All free text is scrubbed — HTML/angle-brackets and
control characters stripped, token-like strings redacted, length-capped — before
being appended as one plain-text block to `<log_dir>/bug_reports.log`. That file
is never rendered as HTML, so reports are XSS-safe by construction; stripping
newlines also prevents forged/injected log entries.

Lightly hardened against abuse (it's public): a per-IP rate limit, a payload
cap (Pydantic max_length), and an Origin/Referer check against the configured
origins.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.report_categories import REPORT_CATEGORIES, normalize

logger = logging.getLogger("app.routers.report")

router = APIRouter(prefix="/api", tags=["report"])

_BUG_LOG = "bug_reports.log"
_MSG_MAX = 2000
_URL_MAX = 300
_UA_MAX = 300

# Best-effort in-memory per-IP rate limit (resets on restart).
_RATE_WINDOW = 3600  # seconds
_RATE_MAX = 20       # reports per IP per window
_rate: dict[str, list[float]] = {}

_TAG_RE = re.compile(r"<[^>]*>")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]+")     # includes \r \n \t — collapse to space
_SECRET_RE = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")  # redact long token-like strings


class ReportIn(BaseModel):
    category: str = Field(default="Other", max_length=40)
    subcategory: str = Field(default="Other", max_length=60)
    message: str = Field(min_length=1, max_length=5000)
    url: str = Field(default="", max_length=500)


def _scrub(text: str, max_len: int) -> str:
    """Make user text safe to store as one plain-text line: drop tags + angle
    brackets, collapse control chars/newlines to spaces (blocks log injection),
    redact token-like strings, and cap length."""
    text = _TAG_RE.sub(" ", text)
    text = text.replace("<", " ").replace(">", " ")
    text = _CTRL_RE.sub(" ", text)
    text = _SECRET_RE.sub("[redacted]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _scrub_url(url: str) -> str:
    url = url.split("?", 1)[0].split("#", 1)[0]  # drop query/fragment (possible tokens)
    return _scrub(url, _URL_MAX)


def _client_ip(request: Request) -> str:
    # Behind the Cloudflare tunnel the socket peer is cloudflared; the real
    # client IP is in CF-Connecting-IP / X-Forwarded-For.
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


def _rate_ok(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _rate.get(ip, []) if now - t < _RATE_WINDOW]
    if len(recent) >= _RATE_MAX:
        _rate[ip] = recent
        return False
    recent.append(now)
    _rate[ip] = recent
    if len(_rate) > 10000:  # bound memory
        _rate.clear()
    return True


def _origin_ok(request: Request) -> bool:
    allowed = settings.cors_origin_list
    if not allowed:
        return True  # origins unset (dev) — don't block
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    return any(origin.startswith(a) for a in allowed)


def _append(block: str) -> None:
    os.makedirs(settings.log_dir, exist_ok=True)
    with open(os.path.join(settings.log_dir, _BUG_LOG), "a", encoding="utf-8") as fh:
        fh.write(block)


@router.post("/report")
async def submit_report(payload: ReportIn, request: Request) -> dict:
    if not _origin_ok(request):
        raise HTTPException(status_code=403, detail="forbidden")
    if not _rate_ok(_client_ip(request)):
        raise HTTPException(status_code=429, detail="too many reports; try again later")

    category, subcategory = normalize(payload.category, payload.subcategory)
    message = _scrub(payload.message, _MSG_MAX)
    if not message:
        raise HTTPException(status_code=422, detail="message is empty after sanitizing")
    url = _scrub_url(payload.url)
    ua = _scrub(request.headers.get("user-agent", ""), _UA_MAX)
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    block = (
        "────────────────────────────────────────\n"
        f"{ts}  [{category} / {subcategory}]\n"
        f"URL: {url or '(none)'}\n"
        f"UA:  {ua or '(none)'}\n"
        f"Msg: {message}\n"
    )
    try:
        await asyncio.to_thread(_append, block)
    except OSError as exc:
        logger.warning("bug report could not be written: %s", exc)
        raise HTTPException(status_code=503, detail="could not record report") from exc

    logger.info("bug report filed [%s / %s]", category, subcategory)
    return {"ok": True}


@router.get("/report/categories")
async def report_categories() -> dict:
    """The category → subcategory allowlist, so the frontend form always matches
    the server's validation (also hard-coded in lib/report-categories.ts)."""
    return REPORT_CATEGORIES
